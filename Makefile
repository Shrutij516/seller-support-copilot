API_DIR := services/api
WEB_DIR := apps/web
INFRA_DIR := infra
# Knowledge Base stack (infra/lib/knowledge-base-stack.ts). kb-* targets call real AWS with
# your own credentials and cost money; nothing (CI included) runs them automatically.
KB_STACK ?= KnowledgeBaseStack
KB_REGION ?= us-east-1
KB_DOCS_DIR := data/policies
# Live RAG checks (eval-retrieval, rag-smoke) call Bedrock with your own AWS session via the
# API's venv (botocore[crt] is a dev dependency, so `aws login` sessions work). Cost money.
RAG_SMOKE_MODEL ?= us.anthropic.claude-haiku-4-5-20251001-v1:0
# Scoped CloudFormation execution policy for `cdk bootstrap` (infra/bootstrap/README.md).
# deploy-policy-* and cdk-bootstrap change real IAM/CloudFormation resources; run by hand only.
CFN_EXEC_POLICY_NAME ?= copilot-cfn-exec
CFN_EXEC_POLICY_FILE := infra/bootstrap/cfn-exec-policy.json
aws_account = $$(aws sts get-caller-identity --query Account --output text)
# The committed policy has {{ACCOUNT_ID}} placeholders: IAM policy variables can't replace the
# account field of an ARN. This renders a copy for the calling account into a private temp file
# (deleted on exit), so the account ID is never written into the repo. Sets $$account, $$rendered.
render_cfn_exec_policy = \
	account=$(aws_account); \
	echo "$$account" | grep -Eq '^[0-9]{12}$$' || { echo "Unexpected account id: '$$account'" >&2; exit 1; }; \
	rendered=$$(mktemp "$${TMPDIR:-/tmp}/cfn-exec-policy.XXXXXX"); \
	trap 'rm -f "$$rendered"' EXIT; \
	sed "s/{{ACCOUNT_ID}}/$$account/g" $(CFN_EXEC_POLICY_FILE) > "$$rendered"; \
	if grep -q '{{' "$$rendered"; then echo "Unrendered placeholder in policy" >&2; exit 1; fi
kb_output = $$(aws cloudformation describe-stacks --region $(KB_REGION) --stack-name $(KB_STACK) \
	--query 'Stacks[0].Outputs[?OutputKey==`$(1)`].OutputValue' --output text)
CLIENT_DIR := packages/api-client
# Uses the pnpm version pinned in package.json via corepack (ships with Node 24).
PNPM ?= corepack pnpm

.PHONY: up down test test-integration lint typecheck migrate dynamodb-init seed coverage openapi openapi-check link-user api-client api-client-check kb-upload kb-ingest deploy-policy-create deploy-policy-update cdk-bootstrap eval-retrieval rag-smoke eval-answers

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

deploy-policy-create: ## Create the scoped CloudFormation execution policy (first time only)
	@set -e; \
	$(render_cfn_exec_policy); \
	aws iam create-policy --policy-name $(CFN_EXEC_POLICY_NAME) \
		--policy-document "file://$$rendered" \
		--description "CloudFormation execution policy for CDK bootstrap: KnowledgeBaseStack only" \
		--query Policy.Arn --output text

deploy-policy-update: ## Publish the policy JSON as the new default version (prunes oldest if at the 5-version limit)
	@set -e; \
	$(render_cfn_exec_policy); \
	arn="arn:aws:iam::$$account:policy/$(CFN_EXEC_POLICY_NAME)"; \
	count=$$(aws iam list-policy-versions --policy-arn "$$arn" --query 'length(Versions)' --output text); \
	if [ "$$count" -ge 5 ]; then \
		oldest=$$(aws iam list-policy-versions --policy-arn "$$arn" \
			--query 'sort_by(Versions[?IsDefaultVersion==`false`], &CreateDate)[0].VersionId' --output text); \
		echo "At 5 versions; deleting oldest non-default version $$oldest"; \
		aws iam delete-policy-version --policy-arn "$$arn" --version-id "$$oldest"; \
	fi; \
	aws iam create-policy-version --policy-arn "$$arn" \
		--policy-document "file://$$rendered" --set-as-default \
		--query 'PolicyVersion.{version:VersionId,default:IsDefaultVersion}' --output json

cdk-bootstrap: ## Bootstrap CDK in us-east-1 with the scoped execution policy instead of AdministratorAccess
	@# Runs from the repo root (no cdk.json) on purpose: inside infra/ the CLI would synth the
	@# app first, which needs budgetEmail context and isn't needed to bootstrap an environment.
	@set -e; \
	account=$(aws_account); \
	$(INFRA_DIR)/node_modules/.bin/cdk bootstrap "aws://$$account/$(KB_REGION)" \
		--cloudformation-execution-policies "arn:aws:iam::$$account:policy/$(CFN_EXEC_POLICY_NAME)"

eval-retrieval: ## Score live KB retrieval on evals/retrieval_golden.jsonl; writes evals/results/
	@set -e; \
	kb_id=$(call kb_output,KnowledgeBaseId); \
	if [ -z "$$kb_id" ] || [ "$$kb_id" = "None" ]; then \
		echo "No KnowledgeBaseId output on stack $(KB_STACK) in $(KB_REGION)." >&2; exit 1; \
	fi; \
	uv run --project $(API_DIR) python evals/calibrate_retrieval.py --kb-id "$$kb_id" --region $(KB_REGION)

rag-smoke: ## One live answer through the route's RAG code path: make rag-smoke Q="question"
	@if [ -z "$(Q)" ]; then echo 'Usage: make rag-smoke Q="your question"' >&2; exit 1; fi
	@set -e; \
	kb_id=$(call kb_output,KnowledgeBaseId); \
	if [ -z "$$kb_id" ] || [ "$$kb_id" = "None" ]; then \
		echo "No KnowledgeBaseId output on stack $(KB_STACK) in $(KB_REGION)." >&2; exit 1; \
	fi; \
	uv run --project $(API_DIR) python scripts/rag_smoke.py --kb-id "$$kb_id" --region $(KB_REGION) \
		--model-id "$(RAG_SMOKE_MODEL)" --question "$(Q)"

eval-answers: ## Run every golden question through the RAG pipeline and score answers; writes evals/results/
	@set -e; \
	kb_id=$(call kb_output,KnowledgeBaseId); \
	if [ -z "$$kb_id" ] || [ "$$kb_id" = "None" ]; then \
		echo "No KnowledgeBaseId output on stack $(KB_STACK) in $(KB_REGION)." >&2; exit 1; \
	fi; \
	uv run --project $(API_DIR) python evals/answer_eval.py --kb-id "$$kb_id" --region $(KB_REGION) \
		--model-id "$(RAG_SMOKE_MODEL)"
