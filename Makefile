API_DIR := services/api
WEB_DIR := apps/web
INFRA_DIR := infra
# Uses the pnpm version pinned in apps/web/package.json via corepack (ships with Node 24).
PNPM ?= corepack pnpm

.PHONY: up down test test-integration lint typecheck migrate dynamodb-init seed coverage openapi openapi-check link-user

up: ## Start Postgres, DynamoDB Local, and the API; wait until healthy
	docker compose up -d --build --wait

down: ## Stop the stack (keeps the Postgres volume; add -v to drop it)
	docker compose down

migrate: ## Apply Alembic migrations to the running Postgres (run `make up` first)
	cd $(API_DIR) && AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=dummy AWS_SECRET_ACCESS_KEY=dummy \
		uv run alembic upgrade head

dynamodb-init: ## Create the local "chat" DynamoDB table (idempotent; run `make up` first)
	cd $(API_DIR) && AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=dummy AWS_SECRET_ACCESS_KEY=dummy \
		DYNAMODB_ENDPOINT_URL=http://localhost:8001 uv run python -m copilot_api.scripts.dynamodb_init

seed: migrate ## Seed deterministic synthetic data (sellers, listings, orders); refuses if APP_ENV=prod
	cd $(API_DIR) && AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=dummy AWS_SECRET_ACCESS_KEY=dummy \
		uv run python -m copilot_api.scripts.seed

link-user: ## Link a seed seller to a Cognito sub: make link-user EMAIL=<email> SUB=<sub>
	@if [ -z "$(EMAIL)" ] || [ -z "$(SUB)" ]; then \
		echo "Usage: make link-user EMAIL=<seed seller email> SUB=<cognito sub>" >&2; \
		exit 1; \
	fi
	cd $(API_DIR) && AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=dummy AWS_SECRET_ACCESS_KEY=dummy \
		uv run python -m copilot_api.scripts.link_user --email "$(EMAIL)" --sub "$(SUB)"

test: ## Unit tests (no external dependencies); reports coverage
	cd $(API_DIR) && uv run pytest --cov=copilot_api --cov-report=term-missing
	cd $(INFRA_DIR) && npm test

test-integration: migrate dynamodb-init ## Integration tests against the compose stack (run `make up` first)
	cd $(API_DIR) && AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=dummy AWS_SECRET_ACCESS_KEY=dummy \
		DYNAMODB_ENDPOINT_URL=http://localhost:8001 \
		uv run pytest -m integration --cov=copilot_api --cov-append --cov-report=term-missing

coverage: test test-integration ## Combined unit + integration coverage; fails under 85% for services/api
	cd $(API_DIR) && uv run coverage report --fail-under=85

openapi: ## Regenerate services/api/openapi.json from the current app
	cd $(API_DIR) && AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=dummy AWS_SECRET_ACCESS_KEY=dummy \
		uv run python -m copilot_api.scripts.export_openapi

openapi-check: ## Fail if openapi.json is out of date with the code (used by CI)
	cd $(API_DIR) && AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=dummy AWS_SECRET_ACCESS_KEY=dummy \
		uv run python -m copilot_api.scripts.export_openapi
	git diff --exit-code -- $(API_DIR)/openapi.json

lint:
	cd $(API_DIR) && uv run ruff check . && uv run ruff format --check .
	cd $(WEB_DIR) && $(PNPM) lint

typecheck:
	cd $(API_DIR) && uv run mypy
	cd $(WEB_DIR) && $(PNPM) typecheck
	cd $(INFRA_DIR) && npm run build
