"""Integration tests for validated API behavior."""

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.v1.endpoints import router
from core.database import Base, get_db


def create_test_client() -> TestClient:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_database() -> Iterator[Session]:
        database = testing_session()
        try:
            yield database
        finally:
            database.close()

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_database
    return TestClient(app)


def test_model_create_uses_documented_api_path() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/models",
        json={"huggingface_repo": "example/model", "friendly_name": "Example"},
    )

    assert response.status_code == 200
    assert response.json()["huggingface_repo"] == "example/model"
    assert client.get("/api/v1/v1/models").status_code == 404


def test_model_create_rejects_unvalidated_database_fields() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/models",
        json={
            "huggingface_repo": "example/model",
            "friendly_name": "Example",
            "model_weight_memory_bytes": 123,
        },
    )

    assert response.status_code == 422


def test_profile_requires_existing_model() -> None:
    client = create_test_client()

    response = client.post(
        "/api/v1/profiles",
        json={"model_id": 999, "name": "Missing model"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Model not found"


def test_runtime_sync_snapshot_and_known_good_persistence(monkeypatch) -> None:
    snapshot = {
        "host": {"hostname": "test"},
        "gpus": [],
        "runtime": {
            "container": "vllm",
            "container_health": "healthy",
            "environment": {
                "MODEL_ID": "owner/model",
                "SERVED_MODEL_NAME": "served-model",
                "MAX_MODEL_LEN": "32768",
                "GPU_MEMORY_UTILIZATION": "0.8",
            },
        },
        "vllm": {
            "api_healthy": True,
            "metrics_healthy": True,
            "active_model": "owner/model",
            "served_model_name": "served-model",
            "configured_max_model_len": 32768,
            "effective_max_model_len": 32768,
        },
        "memory": {},
        "lifecycle_preview": {},
    }

    class Discovery:
        def discover(self) -> dict:
            return snapshot

    monkeypatch.setattr("api.v1.endpoints.CapabilityDiscoveryService", Discovery)
    client = create_test_client()

    synced = client.post("/api/v1/runtime/sync")
    captured = client.post("/api/v1/runtime/snapshots")
    promoted = client.post(
        "/api/v1/runtime/known-good",
        json={
            "profile_id": synced.json()["profile_id"],
            "runtime_snapshot_id": captured.json()["id"],
        },
    )

    assert synced.status_code == 200
    assert captured.json()["requested"]["max_model_len"] == "32768"
    assert promoted.status_code == 200
    assert promoted.json()["health_validated"] is True
    assert promoted.json()["restore_available"] is False
