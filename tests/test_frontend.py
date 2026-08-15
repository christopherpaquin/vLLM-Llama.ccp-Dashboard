"""Smoke tests for the appliance dashboard shell."""

from fastapi.testclient import TestClient

from main import app


def test_dashboard_is_served_at_root() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Infrence Engine Dashboard" in response.text
    assert "vLLM DASHBOARD" not in response.text
    assert "Runtime overview" not in response.text
    assert "styles.css?v=2" in response.text
    assert "app.js?v=3" in response.text
    assert "ACTIVE MODEL" in response.text
    assert "TOTAL RAM" in response.text
    assert 'id="host-ip"' in response.text
    assert 'id="host-gpu"' in response.text
    assert 'id="host-engine"' in response.text
    assert "Run TTFT + token rate test" in response.text


def test_host_layout_keeps_identity_left_and_facts_right() -> None:
    styles = TestClient(app).get("/assets/styles.css")

    assert styles.status_code == 200
    assert ".host { display:flex" in styles.text
    assert "justify-content:flex-end" in styles.text
    assert ".host-identity { flex:0 1 40%" in styles.text


def test_dropdown_script_has_loading_empty_and_error_states() -> None:
    page = TestClient(app).get("/")
    response = TestClient(app).get("/assets/app.js")

    assert response.status_code == 200
    assert "Loading cached models" in page.text
    assert "No cached models found" in response.text
    assert "Cached models unavailable" in response.text


def test_runtime_details_are_backend_specific() -> None:
    response = TestClient(app).get("/assets/app.js")

    assert response.status_code == 200
    assert 'backend.type === "llama_cpp"' in response.text
    assert 'addField("GPU layers", env.LLAMA_ARG_N_GPU_LAYERS)' in response.text
    assert 'addField("Parallel slots", vllm.maximum_concurrency)' in response.text
    assert 'addField("Extra vLLM args", env.EXTRA_VLLM_ARGS)' in response.text
