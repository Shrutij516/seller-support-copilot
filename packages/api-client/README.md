# api-client

TypeScript client generated from `services/api/openapi.json`, so the web app and the backend
share one contract instead of hand-typed fetch calls drifting from what the API actually
returns.

```bash
pnpm --filter @copilot/api-client run generate   # regenerate src/generated.ts
```

Or from the repo root: `make api-client`. CI regenerates and diffs against what's committed;
a stale generated client fails the build the same way a stale `openapi.json` does.

`src/generated.ts` is openapi-typescript output: types only, no runtime code, safe to import
without the API running. `src/index.ts` wraps it with `openapi-fetch`: `createApiClient(baseUrl,
middleware)` returns a typed client; callers (apps/web) supply their own auth middleware rather
than this package knowing anything about how a caller authenticates.
