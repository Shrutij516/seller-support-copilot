# Seller Support Copilot

An AI support assistant that helps e-commerce sellers get answers about marketplace policies, their orders, and their listings.

> **Work in progress.** Phases 0 through 3 (data layer, API, frontend) are built and tested. Phases 4 through 9 (Bedrock, evals, observability, end-to-end tests, deployment, and measured results) are planned, not built. See the roadmap below for exactly what that means per phase.

## Architecture

The diagram below is the **full planned system**, not what is deployed today. Nothing in this repo is currently running in AWS; see [Cost and teardown](#cost-and-teardown) and the roadmap for what actually exists yet.

```mermaid
flowchart TB
    Browser["Browser (Next.js app)"]

    subgraph FrontendHosting["Frontend hosting"]
        CF["CloudFront"]
        S3W["S3 (static export)"]
    end

    subgraph AuthLayer["Auth"]
        Cognito["Cognito<br/>(hosted login, JWT issuer)"]
    end

    subgraph Backend["Backend (ECS Fargate)"]
        API["FastAPI"]
        ADOT["ADOT collector<br/>(OpenTelemetry sidecar)"]
    end

    subgraph DataLayer["Data"]
        PG[("Postgres<br/>sellers, listings, orders, cases")]
        DDB[("DynamoDB<br/>chat sessions/messages")]
    end

    subgraph AI["Bedrock"]
        KB["Knowledge Base<br/>(ingested policy docs)"]
        GR["Guardrails"]
        Tools["Tool calling<br/>(seller/order data lookups)"]
    end

    subgraph Obs["Observability"]
        XRay["X-Ray (traces)"]
        CW["CloudWatch (metrics, logs)"]
    end

    subgraph CICD["CI/CD"]
        GHA["GitHub Actions<br/>lint, typecheck, tests, CDK synth"]
    end

    Browser -->|static assets| CF --> S3W
    Browser -->|hosted login| Cognito
    Browser -->|REST, Bearer JWT| API
    API -->|verify JWT via JWKS| Cognito
    API --> PG
    API --> DDB
    API --> KB
    API --> GR
    API --> Tools
    Tools --> PG
    API --> ADOT
    ADOT --> XRay
    ADOT --> CW
    GHA -.->|build and test on every push| Backend
    GHA -.->|build and test on every push| FrontendHosting
```

Today, locally: the browser talks to a FastAPI process (in Docker or run directly), which talks to a real Postgres and a real DynamoDB, both running in Docker (`postgres`, `amazon/dynamodb-local`). Auth against Cognito is real (a real User Pool), everything else in the diagram outside "Frontend hosting", "Backend", "Auth", and "Data" is not built yet.

## Tech stack

- **Frontend**: Next.js (App Router, static export), TypeScript, Tailwind CSS v4, TanStack Query, oidc-client-ts, Vitest + React Testing Library
- **Backend**: FastAPI (Python 3.12), SQLAlchemy 2.0 + Alembic, Pydantic v2, pytest
- **Data**: Postgres (relational: sellers, listings, orders, order_items, support_cases), DynamoDB (chat sessions/messages)
- **Auth**: Amazon Cognito (Authorization Code + PKCE, JWT verified in-process against JWKS)
- **AI** (planned): Amazon Bedrock, Knowledge Bases, Guardrails, tool calling, structured outputs
- **Observability** (planned): OpenTelemetry, ADOT collector, CloudWatch, X-Ray
- **Infra**: Docker Compose (local), AWS CDK (`infra/`, currently only a budget/cost-alert stack), ECS Fargate + S3/CloudFront (planned)
- **CI/CD**: GitHub Actions (lint, typecheck, unit and integration tests, Docker build check, CDK synth on every push)

See [DECISIONS.md](DECISIONS.md) for why each of these was chosen and what was rejected.

## Roadmap

| Phase | Status | Delivers |
| --- | --- | --- |
| 0 | Done | Monorepo scaffolding: repo layout, Docker Compose (Postgres, DynamoDB Local, API), GitHub Actions CI skeleton, CDK `BudgetStack` for cost alerts |
| 1 | Done | Data layer: Postgres schema (sellers, listings, orders, order_items, support_cases) via SQLAlchemy + Alembic, DynamoDB chat store, deterministic seed script, refund-request service with row-level locking |
| 2 | Done | API: Cognito JWT verification and role-based access, REST endpoints under `/v1`, RFC 9457 `application/problem+json` errors, OpenAPI contract exported and checked in CI, 85% coverage gate |
| 3 | Done | Frontend: Next.js static export, Cognito Authorization Code + PKCE login, generated TypeScript API client, seller and admin pages (orders, cases, chat, admin case queue), accessibility (Lighthouse 100/100 on the pages audited), Vitest test suite |
| 4 | Planned | Bedrock: Knowledge Base retrieval over ingested policy docs, Guardrails, tool calling against seller/order data, structured outputs |
| 5 | Planned | Eval harness: golden question set with expected facts, run on demand and gating CI on regression |
| 6 | Planned | Observability: OpenTelemetry instrumentation in the API, ADOT sidecar forwarding traces to X-Ray and metrics/logs to CloudWatch |
| 7 | Planned | End-to-end tests: Playwright driving the web app in a real browser |
| 8 | Planned | Deploy: FastAPI on ECS Fargate behind an ALB, Next.js static export on S3 + CloudFront |
| 9 | Planned | Results: measure and report p95 latency, cost per query, eval pass rate, and final test coverage against the deployed system |
| Stretch | Not started | SQS for async policy-document ingestion, CDK for infra beyond the budget stack, a Lambda ingestion worker, rate limiting at the API Gateway/WAF layer. Redis was evaluated and cut (no measured hot path to justify it); see [DECISIONS.md](DECISIONS.md#cut-or-deferred). |

## Design decisions

Every non-obvious choice in this repo, what it does, why it was chosen over the alternatives, the tradeoff accepted, and when to revisit it, is recorded in [DECISIONS.md](DECISIONS.md). That includes both what's built (FastAPI, Postgres, DynamoDB key design, Cognito, keyset pagination, the admin case queue's ordering, `oidc-client-ts`, TanStack Query, and more) and what's planned (Bedrock, the eval harness, OpenTelemetry, ECS Fargate, Playwright).

## Repository layout

| Path | What |
| --- | --- |
| `apps/web` | Next.js frontend (static export for S3 + CloudFront) |
| `services/api` | FastAPI backend |
| `services/ingest` | Document ingestion pipeline (placeholder, phase 4) |
| `packages/api-client` | TypeScript API client generated from `services/api/openapi.json` |
| `infra` | AWS CDK app (currently `BudgetStack` only; not deployed by CI) |
| `evals` | Evaluation datasets and scripts (placeholder, phase 5) |
| `data` | Synthetic sample data, including the fictional marketplace's policy docs used by seeding and (later) the Bedrock Knowledge Base |
| `DECISIONS.md` | What each component does, why it was chosen, and what was rejected |

## How to run locally

### Prerequisites

- Docker (with Compose v2)
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node 24 (see `.nvmrc`); pnpm via corepack (`corepack pnpm`, or `corepack enable`)
- Optional: [pre-commit](https://pre-commit.com/) (`pre-commit install`)

### Backend

```bash
make up             # Postgres, DynamoDB Local, API on :8000 (docker compose, rebuilds the API image)
make migrate         # apply Alembic migrations
make dynamodb-init   # create the local "chat" DynamoDB table
make seed            # deterministic synthetic sellers/listings/orders/cases (refuses if APP_ENV=prod)
make link-user EMAIL=<seed seller email> SUB=<cognito sub>   # link a seeded seller to a real Cognito user for local login
```

### Frontend

```bash
corepack pnpm install                          # from the repo root (pnpm workspace)
cp apps/web/.env.example apps/web/.env.local    # fill in Cognito values
corepack pnpm --filter @copilot/web run dev     # http://localhost:3000, needs the API running
```

### Checks

```bash
make lint               # ruff (api) + eslint (web)
make typecheck           # mypy (api) + tsc (api-client, web) + CDK build (infra)
make test                # unit tests: pytest (api, no external deps) + CDK tests
make test-integration    # integration tests: pytest -m integration (needs `make up`)
make coverage            # unit + integration coverage for services/api; fails under 85%
make openapi-check       # fails if openapi.json is stale
make api-client-check    # fails if the generated TS client is stale
corepack pnpm --filter @copilot/web run test    # Vitest
```

Other targets: `make down` (stop containers, keeps the Postgres volume), `make openapi` / `make api-client` (regenerate without the drift check).

## Cost and teardown

- Local development costs nothing. `make down` stops containers; `docker compose down -v` also deletes the Postgres volume.
- Nothing is deployed to AWS automatically. CI only runs `cdk synth`.
- Deploy the budget first so spend is tracked from day one (default 25 USD/month, email alerts at 50%, 80%, 100% actual and 100% forecasted):
  `cd infra && npx cdk deploy BudgetStack -c budgetEmail=you@example.com`
- Teardown: `cd infra && npx cdk destroy --all -c budgetEmail=you@example.com`. Later phases will add billable resources (Bedrock, databases, Fargate); destroy them when not in use.

## Results

Nothing in this section is measured yet; these are placeholders for phase 9, once the system is deployed and there's real traffic and a real eval run to measure.

| Metric | Value |
| --- | --- |
| p95 latency | To be measured in Phase 9 |
| Cost per query | To be measured in Phase 9 |
| Eval pass rate | To be measured in Phase 9 |
| Test coverage (`services/api`, unit + integration) | 90% (gate: 85%), measured locally via `make coverage` |
