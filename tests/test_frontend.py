"""Smoke tests for the appliance dashboard shell."""

from fastapi.testclient import TestClient

from main import app


def test_dashboard_is_served_at_root() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "ACTIVE MODEL" in response.text
    assert "TOTAL RAM" in response.text
    assert 'id="host-ip"' in response.text
    assert "Run TTFT + token rate test" in response.text


def test_dropdown_script_has_loading_empty_and_error_states() -> None:
    page = TestClient(app).get("/")
    response = TestClient(app).get("/assets/app.js")

    assert response.status_code == 200
    assert "Loading cached models" in page.text
    assert "No cached models found" in response.text
    assert "Cached models unavailable" in response.text
