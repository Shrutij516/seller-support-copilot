# copilot-api

FastAPI service for Seller Support Copilot.

```bash
uv sync
uv run uvicorn copilot_api.main:app --reload   # http://localhost:8000/docs
uv run alembic upgrade head                    # apply migrations (needs `make up` first)
uv run pytest                                  # unit tests
uv run pytest -m integration                   # needs `make up`, `make migrate`, `make dynamodb-init` first
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

Endpoints: `GET /healthz` (liveness, no dependencies), `GET /readyz` (checks Postgres and the DynamoDB `chat` table, 503 naming the failed dependency).

From the repo root: `make migrate` applies Alembic migrations, `make dynamodb-init` creates the
local "chat" DynamoDB table, `make seed` loads deterministic synthetic sellers/listings/orders
(refuses if `APP_ENV=prod`).
