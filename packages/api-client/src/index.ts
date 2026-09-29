// `generated.ts` is produced by `pnpm generate` (openapi-typescript against
// services/api/openapi.json) and committed, not built on the fly, so a consumer never needs
// the API running or the codegen toolchain just to typecheck.
import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./generated";

export type { paths, components, operations } from "./generated";
export type { Middleware } from "openapi-fetch";

export function createApiClient(baseUrl: string, middleware: Middleware[] = []) {
  const client = createClient<paths>({ baseUrl });
  for (const mw of middleware) {
    client.use(mw);
  }
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;
