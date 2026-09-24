# ADR 0001: Backend language and framework

- Status: Accepted
- Date: 2026-09-24

## Context

Seller Support Copilot needs an HTTP API for chat, retrieval, and seller data (policies, orders, listings). It is a portfolio project built in short phases, so time to a working, well-tested slice matters more than long-term team scaling.

- Timeline: a small scope delivered in weeks, by one developer.
- The AI parts (AWS Bedrock calls, retrieval, evaluation harnesses) have the most mature tooling in Python: boto3, eval libraries, notebooks for error analysis.
- The author has deep Java and Spring Boot experience, so Spring Boot would be the familiar choice.

Alternatives considered:

1. **Spring Boot (Java 21+)**: strongest personal expertise, excellent typing and ops story. But Bedrock and eval work would either be written in Java with thinner libraries or split into a second Python service early.
2. **FastAPI (Python 3.12)**: one language for API, ingestion, and evals; typed request/response models via Pydantic; OpenAPI generated from code.
3. **Node (Fastify/Nest)**: shares a language with the web app, but has the same AI tooling gap as Java.

## Decision

Use FastAPI on Python 3.12, managed with uv, with ruff and mypy in strict mode to recover some of the safety Java would give by default.

The generated OpenAPI spec is the contract between the web app and the backend. The TypeScript client in `packages/api-client` will be generated from it, so the backend can be replaced without touching the front end as long as the spec holds.

## Consequences

- One language across API, ingestion, and evals; Bedrock and eval code can be shared directly.
- Showcases Python depth in addition to existing Java depth.
- Weaker compile-time guarantees than Java; mitigated by strict mypy, Pydantic models, and tests in CI.
- Async Python needs care: blocking calls inside request handlers will stall the event loop.

## Revisit if

- The API grows into heavy transactional domain logic where Spring's ecosystem clearly wins.
- Latency or throughput targets are missed and profiling points at the Python runtime.
- A team with mostly Java skills takes over the service.
