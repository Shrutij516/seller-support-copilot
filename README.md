# Seller Support Copilot

An AI support assistant that helps e-commerce sellers get answers about marketplace policies, their orders, and their listings.

Status: Phase 0 (scaffolding). Core stack: Next.js + TypeScript, FastAPI, Postgres, DynamoDB, Cognito,
AWS Bedrock (Knowledge Bases, Guardrails, tool calling, structured outputs), OpenTelemetry +
CloudWatch/X-Ray, pytest + Playwright, Docker, GitHub Actions, ECS Fargate. SQS and CDK are stretch
goals, added after the core works. See [DECISIONS.md](DECISIONS.md) for what each piece does and why.

## Repository layout

| Path                  | What                                                                                    |
| --------------------- | --------------------------------------------------------------------------------------- |
| `apps/web`            | Next.js front end (static export for S3 + CloudFront)                                   |
| `services/api`        | FastAPI backend                                                                         |
| `services/ingest`     | Document ingestion (placeholder)                                                        |
| `packages/api-client` | Generated TypeScript API client (placeholder)                                           |
| `infra`               | AWS CDK app (currently `BudgetStack`); parked, not deployed until CDK moves off stretch |
| `evals`, `data`       | Evaluation suites and sample data (placeholders)                                        |
| `DECISIONS.md`        | What each component does, why we chose it, and what we rejected                         |

## Prerequisites

- Docker (with Compose v2)
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node 24 (see `.nvmrc`); pnpm is used via corepack (`corepack pnpm`, or `corepack enable`)
- Optional: [pre-commit](https://pre-commit.com/) (`pre-commit install`)

## Local setup

```bash
make up                                                      # Postgres, DynamoDB Local, API on :8000
make test && make test-integration                           # unit, then integration tests
cp apps/web/.env.example apps/web/.env.local
cd apps/web && corepack pnpm install && corepack pnpm dev    # web on :3000
```

Other targets: `make lint`, `make typecheck`, `make down`.

## Cost and teardown

- Local development costs nothing. `make down` stops containers; `docker compose down -v` also deletes the Postgres volume.
- Nothing is deployed to AWS automatically. CI only runs `cdk synth`.
- Deploy the budget first so spend is tracked from day one (default 25 USD/month, email alerts at 50%, 80%, 100% actual and 100% forecasted):
  `cd infra && npx cdk deploy BudgetStack -c budgetEmail=you@example.com`
- Teardown: `cd infra && npx cdk destroy --all -c budgetEmail=you@example.com`. Later phases will add billable resources (Bedrock, databases); destroy them when not in use.
