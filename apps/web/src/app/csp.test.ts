import { afterEach, describe, expect, it, vi } from "vitest";
import { buildContentSecurityPolicy } from "./csp";

const LIVE = {
  NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000",
  NEXT_PUBLIC_COGNITO_AUTHORITY: "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_EXAMPLE",
  NEXT_PUBLIC_COGNITO_DOMAIN: "https://example-prefix.auth.us-east-1.amazoncognito.com",
};

function directive(policy: string, name: string): string[] {
  const entry = policy.split("; ").find((d) => d.startsWith(`${name} `));
  return entry ? entry.split(" ").slice(1) : [];
}

describe("buildContentSecurityPolicy", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("allows exactly the API, Cognito issuer, and hosted-UI origins for fetches", () => {
    for (const [key, value] of Object.entries(LIVE)) vi.stubEnv(key, value);

    const connectSrc = directive(buildContentSecurityPolicy(), "connect-src");

    expect(connectSrc).toEqual([
      "'self'",
      "http://localhost:8000",
      "https://cognito-idp.us-east-1.amazonaws.com",
      "https://example-prefix.auth.us-east-1.amazoncognito.com",
    ]);
  });

  it("allows form posts only to self and the hosted-UI origin", () => {
    for (const [key, value] of Object.entries(LIVE)) vi.stubEnv(key, value);

    expect(directive(buildContentSecurityPolicy(), "form-action")).toEqual([
      "'self'",
      "https://example-prefix.auth.us-east-1.amazoncognito.com",
    ]);
  });

  it("never emits wildcard sources", () => {
    for (const [key, value] of Object.entries(LIVE)) vi.stubEnv(key, value);

    const sources = buildContentSecurityPolicy()
      .split("; ")
      .flatMap((d) => d.split(" ").slice(1));
    expect(sources.filter((s) => s.includes("*"))).toEqual([]);
  });
});
