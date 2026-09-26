# Decisions

Single source of design decisions for Seller Support Copilot. For each component: what it
does, why we chose it, what we rejected, and the tradeoff we're accepting. Update this as we
build; don't let it drift from the code.

## FastAPI (Python 3.12)

- Status: In use
- What it does: Serves the HTTP API (health checks now, chat and seller data later).
- Why we chose it: Python is my strongest language. Bedrock, boto3, and eval tooling are Python-native. My Java is coursework-only and shallow, so a short timeline would only give me Spring Boot knowledge too thin to defend.
- Rejected alternative: Spring Boot (Java). Strong typing and ops story, but not something I can defend in depth, and it would split AI code into a second service.
- Tradeoff we accept: Weaker compile-time guarantees than Java; covered by strict mypy, Pydantic models, and tests.
- Revisit if: The API grows heavy transactional domain logic, or a Java-strong team takes over.

## Next.js static export (S3 + CloudFront)

- Status: In use
- What it does: Builds the web app to static HTML/JS/CSS, served from S3 through CloudFront.
- Why we chose it: The app is just a client of the API; no SEO or SSR need. Static hosting is near-zero cost with nothing to patch or scale.
- Rejected alternative: Next.js server on ECS Fargate. Gives SSR, route handlers, image optimization; not needed here, and costs more to run.
- Tradeoff we accept: No SSR, no `app/api`, no server actions. Each environment needs its own build since env vars are inlined at build time.
- Revisit if: A page needs SSR for SEO, or we need server-side secrets in the front end.

## Postgres

- Status: In use (Docker locally; managed Postgres later)
- What it does: Stores relational, transactional data: sellers, orders, cases, anything needing joins or ACID transactions.
- Why we chose it: Mature, well understood, strong consistency for data that has real relationships.
- Rejected alternative: DynamoDB for everything. Would force denormalized, single-table modeling onto data that's naturally relational.
- Tradeoff we accept: Schema migrations to manage, and vertical scaling limits versus a fully managed NoSQL store.
- Revisit if: One relational table's write volume becomes the bottleneck and its access pattern is simple enough for DynamoDB.

## DynamoDB

- Status: In use (DynamoDB Local for dev)
- What it does: Stores chat sessions and message history.
- Why we chose it: The access pattern is simple and key-based (append a message, read a session's history by session ID, no joins), and old sessions can expire via TTL. That fits key-value better than relational tables.
- Rejected alternative: Postgres tables for chat history. Works, but couples an append-only, high-churn workload to the same database handling transactional seller/order data.
- Tradeoff we accept: No cross-store transactions with Postgres. Any workflow touching both stores needs eventual consistency, and access patterns must be designed up front since DynamoDB has no ad hoc queries.
- Revisit if: We need to join chat data with relational data in one transaction, or query needs outgrow key-based access.

## Cognito

- Status: Planned (phase 1)
- What it does: Handles seller/admin signup and login, issues tokens carrying the role.
- Why we chose it: Managed auth with native AWS integration; I don't build or store passwords myself.
- Rejected alternative: Custom auth (JWT plus a users table). More code to secure and maintain for something Cognito already does.
- Tradeoff we accept: Less UI and token customization than rolling it myself; some config lives outside app code.
- Revisit if: Auth needs (SSO, custom MFA) outgrow what Cognito supports cleanly.

## Bedrock (Knowledge Bases, Guardrails, tool calling, structured outputs)

- Status: Planned (phase 1+)
- What it does: Knowledge Bases retrieve from ingested policy docs; Guardrails filter unsafe input/output; tool calling lets the model query seller/order data; structured outputs give the API typed, validated responses.
- Why we chose it: Managed retrieval and safety instead of a hand-built RAG pipeline and moderation layer.
- Rejected alternative: Self-hosted RAG (own vector DB, prompt-based guardrails). More to build and secure, no managed safety filtering.
- Tradeoff we accept: Vendor lock-in to Bedrock's APIs and models; less control over retrieval internals.
- Revisit if: Retrieval quality or cost doesn't hold up under real evals.

## OpenTelemetry + CloudWatch/X-Ray

- Status: Planned (phase 1+)
- What it does: OpenTelemetry instruments the API for traces, metrics, and logs; CloudWatch stores them; X-Ray visualizes traces end to end.
- Why we chose it: Vendor-neutral instrumentation with native AWS backends, so nothing extra to run.
- Rejected alternative: A third-party observability vendor (Datadog, Honeycomb). Nicer UX in places, but another paid service to integrate.
- Tradeoff we accept: X-Ray's tracing UI is less polished than dedicated vendors.
- Revisit if: Cross-service debugging gets painful enough to justify a dedicated vendor.

## Docker

- Status: In use
- What it does: Packages the API into containers; docker-compose runs Postgres, DynamoDB Local, and the API together for local dev.
- Why we chose it: Reproducible local environment, and the same image ships to ECS Fargate later.
- Rejected alternative: Bare local processes. Simpler at first, but drifts from what actually deploys.
- Tradeoff we accept: A build step and image to manage; local dev needs Docker running.
- Revisit if: Not expected at this scale.

## GitHub Actions

- Status: In use
- What it does: Runs lint, typecheck, unit and integration tests, a Docker build check, and CDK synth on every PR and push to main.
- Why we chose it: Free for this repo, lives next to the code, no separate CI system to run.
- Rejected alternative: A hosted CI vendor (CircleCI, Buildkite). No real benefit here, one more account to manage.
- Tradeoff we accept: Limited free minutes at larger scale; not a concern at this size.
- Revisit if: Build times or minutes become a real constraint.

## ECS Fargate

- Status: Planned (phase 2+, deploy)
- What it does: Runs the FastAPI container in production without managing servers.
- Why we chose it: Serverless containers, scales to near-zero when idle, same Docker image as local dev.
- Rejected alternative: Lambda. Cheaper at very low volume, but cold starts and a 15-minute limit fit a long-lived API poorly.
- Tradeoff we accept: Costs more per request than Lambda at very low traffic; more setup (task definitions, ALB).
- Revisit if: Traffic is low and spiky enough that Lambda's pay-per-invocation wins on cost.

## pytest + Playwright

- Status: In use (pytest); Planned (Playwright, phase 1+)
- What it does: pytest covers the API (unit and integration). Playwright will drive the web app in a real browser for end-to-end checks.
- Why we chose it: pytest is the Python standard; Playwright has good modern ergonomics and CI support.
- Rejected alternative: Selenium for e2e. Playwright is less flaky in CI with a nicer API.
- Tradeoff we accept: Two test stacks to maintain (Python for API, TypeScript for e2e).
- Revisit if: The e2e suite becomes a maintenance burden relative to what it catches.

## Monorepo layout

- Status: In use
- What it does: One repo holds apps/web, services/api, services/ingest, packages/api-client, infra, evals, and data.
- Why we chose it: One developer, one project. A single CI pipeline and one place to see the whole system, with easy cross-cutting changes (API contract and client together).
- Rejected alternative: Separate repos per service. Coordination overhead with no team-size benefit yet.
- Tradeoff we accept: One CI pipeline runs longer as services are added; will need path filters eventually.
- Revisit if: Multiple people start owning different services independently.

## Cut or deferred

- **Redis**: Cut. No measured latency problem to justify a cache. Add back only if profiling shows a real hot path.
- **SQS**: Stretch. Needed for async policy-document ingestion into the Bedrock Knowledge Base; ingestion runs synchronously until the core product works.
- **CDK**: Stretch. `infra/` stays in the repo (currently just `BudgetStack`) but new infra is deployed by hand until CDK earns its place; its CI job keeps running so it doesn't rot.
- **Lambda**: Not needed. ECS Fargate fits a long-lived API better; nothing here is a short, bursty, event-triggered job.
- **Spring Boot**: Rejected. Strongest expertise on paper, but the Java behind it is coursework-only and shallow; FastAPI is the more defensible choice for this timeline.
