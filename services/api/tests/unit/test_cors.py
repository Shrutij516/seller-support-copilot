from fastapi.testclient import TestClient

from copilot_api.main import app

client = TestClient(app)


def test_allowed_origin_gets_cors_header() -> None:
    response = client.get("/healthz", headers={"Origin": "http://localhost:3000"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_disallowed_origin_gets_no_cors_header() -> None:
    response = client.get("/healthz", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in response.headers
