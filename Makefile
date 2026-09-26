API_DIR := services/api
WEB_DIR := apps/web
INFRA_DIR := infra
# Uses the pnpm version pinned in apps/web/package.json via corepack (ships with Node 24).
PNPM ?= corepack pnpm

.PHONY: up down test test-integration lint typecheck

up: ## Start Postgres, DynamoDB Local, and the API; wait until healthy
	docker compose up -d --build --wait

down: ## Stop the stack (keeps the Postgres volume; add -v to drop it)
	docker compose down

test: ## Unit tests (no external dependencies)
	cd $(API_DIR) && uv run pytest
	cd $(INFRA_DIR) && npm test

test-integration: ## Integration tests against the compose stack (run `make up` first)
	cd $(API_DIR) && AWS_REGION=us-east-1 AWS_ACCESS_KEY_ID=dummy AWS_SECRET_ACCESS_KEY=dummy \
		uv run pytest -m integration

lint:
	cd $(API_DIR) && uv run ruff check . && uv run ruff format --check .
	cd $(WEB_DIR) && $(PNPM) lint

typecheck:
	cd $(API_DIR) && uv run mypy
	cd $(WEB_DIR) && $(PNPM) typecheck
	cd $(INFRA_DIR) && npm run build
