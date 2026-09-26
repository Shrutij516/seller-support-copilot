import os

import pytest
from fastapi.testclient import TestClient

from copilot_api.config import Settings, get_settings
from copilot_api.main import app

pytestmark = pytest.mark.integration

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://copilot:copilot@localhost:5432/copilot")
DYNAMODB_ENDPOINT_URL = os.environ.get("DYNAMODB_ENDPOINT_URL", "http://localhost:8001")
# Nothing listens on port 1, so connections are refused immediately.
UNREACHABLE_DYNAMODB_ENDPOINT_URL = "http://localhost:1"


def _client_with(settings: Settings) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides() -> None:
    app.dependency_overrides.clear()


def test_readyz_ok_when_dependencies_up() -> None:
    client = _client_with(
        Settings(database_url=DATABASE_URL, dynamodb_endpoint_url=DYNAMODB_ENDPOINT_URL)
    )
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "ok", "dynamodb": "ok"}}


def test_readyz_503_names_failed_dependency() -> None:
    client = _client_with(
        Settings(database_url=DATABASE_URL, dynamodb_endpoint_url=UNREACHABLE_DYNAMODB_ENDPOINT_URL)
    )
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {
        "status": "fail",
        "checks": {"postgres": "ok", "dynamodb": "fail"},
        "failed": ["dynamodb"],
    }
