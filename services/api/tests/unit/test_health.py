from fastapi.testclient import TestClient

from copilot_api.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generates_request_id_when_missing() -> None:
    response = client.get("/healthz")
    assert len(response.headers["X-Request-ID"]) == 32


def test_echoes_valid_request_id() -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_replaces_unsafe_request_id() -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "bad id\twith spaces"})
    assert response.headers["X-Request-ID"] != "bad id\twith spaces"
