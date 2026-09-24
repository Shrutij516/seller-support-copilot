# copilot-api

FastAPI service for Seller Support Copilot.

```bash
uv sync
uv run uvicorn copilot_api.main:app --reload   # http://localhost:8000/docs
uv run pytest                                  # unit tests
uv run pytest -m integration                   # needs `make up` first
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Endpoints: `GET /healthz` (liveness, no dependencies), `GET /readyz` (checks Postgres and Redis, 503 on failure).
