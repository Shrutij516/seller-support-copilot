API_DIR := services/api
WEB_DIR := apps/web
INFRA_DIR := infra
# Knowledge Base stack (infra/lib/knowledge-base-stack.ts). kb-* targets call real AWS with
# your own credentials and cost money; nothing (CI included) runs them automatically.
KB_STACK ?= KnowledgeBaseStack
KB_REGION ?= us-east-1
KB_DOCS_DIR := data/policies
kb_output = $$(aws cloudformation describe-stacks --region $(KB_REGION) --stack-name $(KB_STACK) \
	--query 'Stacks[0].Outputs[?OutputKey==`$(1)`].OutputValue' --output text)
CLIENT_DIR := packages/api-client
# Uses the pnpm version pinned in package.json via corepack (ships with Node 24).
PNPM ?= corepack pnpm

.PHONY: up down test test-integration lint typecheck migrate dynamodb-init seed coverage openapi openapi-check link-user api-client api-client-check kb-upload kb-ingest

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

api-client: ## Regenerate the TypeScript client from services/api/openapi.json
	$(PNPM) --filter @copilot/api-client run generate

api-client-check: ## Fail if the generated client is stale (used by CI)
	$(PNPM) --filter @copilot/api-client run generate
	git diff --exit-code -- $(CLIENT_DIR)/src/generated.ts

lint:
	cd $(API_DIR) && uv run ruff check . && uv run ruff format --check .
	cd $(WEB_DIR) && $(PNPM) lint

typecheck:
	cd $(API_DIR) && uv run mypy
	$(PNPM) --filter @copilot/api-client run typecheck
	cd $(WEB_DIR) && $(PNPM) typecheck
	cd $(INFRA_DIR) && npm run build

kb-upload: ## Mirror data/policies into the KB docs bucket (deletes objects not in the repo)
	@bucket=$(call kb_output,DocsBucketName); \
	if [ -z "$$bucket" ] || [ "$$bucket" = "None" ]; then \
		echo "No DocsBucketName output on stack $(KB_STACK) in $(KB_REGION); deploy it first." >&2; exit 1; \
	fi; \
	echo "Syncing $(KB_DOCS_DIR) -> s3://$$bucket/"; \
	aws s3 sync $(KB_DOCS_DIR) "s3://$$bucket/" --region $(KB_REGION) --delete --exclude "*" --include "*.md"

kb-ingest: ## Start a KB ingestion job and poll until COMPLETE/FAILED; prints statistics
	@set -e; \
	kb_id=$(call kb_output,KnowledgeBaseId); \
	ds_id=$(call kb_output,DataSourceId); \
	if [ -z "$$kb_id" ] || [ "$$kb_id" = "None" ] || [ -z "$$ds_id" ] || [ "$$ds_id" = "None" ]; then \
		echo "No KnowledgeBaseId/DataSourceId outputs on stack $(KB_STACK) in $(KB_REGION)." >&2; exit 1; \
	fi; \
	job_id=$$(aws bedrock-agent start-ingestion-job --region $(KB_REGION) \
		--knowledge-base-id "$$kb_id" --data-source-id "$$ds_id" \
		--query ingestionJob.ingestionJobId --output text); \
	echo "Ingestion job $$job_id started (KB $$kb_id, data source $$ds_id)"; \
	while :; do \
		status=$$(aws bedrock-agent get-ingestion-job --region $(KB_REGION) \
			--knowledge-base-id "$$kb_id" --data-source-id "$$ds_id" --ingestion-job-id "$$job_id" \
			--query ingestionJob.status --output text); \
		echo "  status: $$status"; \
		case "$$status" in COMPLETE|FAILED|STOPPED) break ;; esac; \
		sleep 10; \
	done; \
	aws bedrock-agent get-ingestion-job --region $(KB_REGION) \
		--knowledge-base-id "$$kb_id" --data-source-id "$$ds_id" --ingestion-job-id "$$job_id" \
		--query "ingestionJob.{status:status,statistics:statistics,failureReasons:failureReasons}" \
		--output json; \
	[ "$$status" = "COMPLETE" ]
