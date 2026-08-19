"""Smoke and contract tests for the appliance dashboard shell."""

from fastapi.testclient import TestClient

from main import app


def test_dashboard_is_served_at_root() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "Inference Engine Dashboard" in response.text
    assert "vLLM DASHBOARD" not in response.text
    assert "Runtime overview" not in response.text
    assert "styles.css?v=" in response.text
    assert "app.js?v=" in response.text
    assert "ACTIVE MODEL" in response.text
    assert "TOTAL RAM" in response.text
    assert 'id="host-ip"' in response.text
    assert 'id="host-gpu"' in response.text
    assert 'id="host-engine"' in response.text
    assert "Run TTFT + token rate test" in response.text
    assert 'id="tunables"' in response.text


def test_host_layout_keeps_identity_left_and_facts_right() -> None:
    styles = TestClient(app).get("/assets/styles.css")

    assert styles.status_code == 200
    assert (
        ".host { display: flex" in styles.text or ".host { display:flex" in styles.text
    )
    assert (
        "justify-content: flex-end" in styles.text
        or "justify-content:flex-end" in styles.text
    )
    assert (
        ".host-identity { flex: 0 1 40%" in styles.text
        or ".host-identity { flex:0 1 40%" in styles.text
    )


def test_dropdown_script_has_loading_empty_and_error_states() -> None:
    page = TestClient(app).get("/")
    response = TestClient(app).get("/assets/app.js")

    assert response.status_code == 200
    assert "Loading cached models" in page.text
    assert "No cached models found" in response.text
    assert "Cached models unavailable" in response.text


def test_runtime_details_and_tooltips_in_frontend() -> None:
    response = TestClient(app).get("/assets/app.js")

    assert response.status_code == 200
    assert "renderRuntimeGroups" in response.text
    assert "tooltip-box" in response.text
    assert "info-btn" in response.text
    assert "source-badge" in response.text
    assert "LLAMA_ARG_N_GPU_LAYERS" in response.text
    assert "LLAMA_ARG_CACHE_TYPE_K" in response.text
    assert "GPU_MEMORY_UTILIZATION" in response.text
    assert "ENABLE_PREFIX_CACHING" in response.text
    assert "Flash Attention" in response.text
    assert "Parallel Slots" in response.text
    assert "Microbatch Size" in response.text
