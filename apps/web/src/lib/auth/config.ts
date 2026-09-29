// NEXT_PUBLIC_* values are inlined at build time (static export, no server to read env at
// request time), so a missing one here means the *build* was missing it, not just this
// user's machine. Checked lazily (never at module import time) so a build with one page not
// needing auth doesn't fail just because Cognito config isn't set yet.

export interface AuthConfig {
  authority: string;
  clientId: string;
  redirectUri: string;
  logoutUri: string;
  scope: string;
  cognitoDomain: string;
}

const REQUIRED_VARS = [
  "NEXT_PUBLIC_COGNITO_AUTHORITY",
  "NEXT_PUBLIC_COGNITO_CLIENT_ID",
  "NEXT_PUBLIC_COGNITO_REDIRECT_URI",
  "NEXT_PUBLIC_COGNITO_LOGOUT_URI",
  "NEXT_PUBLIC_COGNITO_SCOPE",
  "NEXT_PUBLIC_COGNITO_DOMAIN",
] as const;

export class AuthConfigError extends Error {
  readonly missing: string[];

  constructor(missing: string[]) {
    super(
      `Missing required auth configuration: ${missing.join(", ")}. Copy apps/web/.env.example to .env.local and fill these in.`,
    );
    this.name = "AuthConfigError";
    this.missing = missing;
  }
}

export function loadAuthConfig(): AuthConfig {
  const values: Record<string, string | undefined> = {
    NEXT_PUBLIC_COGNITO_AUTHORITY: process.env.NEXT_PUBLIC_COGNITO_AUTHORITY,
    NEXT_PUBLIC_COGNITO_CLIENT_ID: process.env.NEXT_PUBLIC_COGNITO_CLIENT_ID,
    NEXT_PUBLIC_COGNITO_REDIRECT_URI: process.env.NEXT_PUBLIC_COGNITO_REDIRECT_URI,
    NEXT_PUBLIC_COGNITO_LOGOUT_URI: process.env.NEXT_PUBLIC_COGNITO_LOGOUT_URI,
    NEXT_PUBLIC_COGNITO_SCOPE: process.env.NEXT_PUBLIC_COGNITO_SCOPE,
    NEXT_PUBLIC_COGNITO_DOMAIN: process.env.NEXT_PUBLIC_COGNITO_DOMAIN,
  };

  const missing = REQUIRED_VARS.filter((key) => !values[key]);
  if (missing.length > 0) {
    throw new AuthConfigError(missing);
  }

  return {
    authority: values.NEXT_PUBLIC_COGNITO_AUTHORITY!,
    clientId: values.NEXT_PUBLIC_COGNITO_CLIENT_ID!,
    redirectUri: values.NEXT_PUBLIC_COGNITO_REDIRECT_URI!,
    logoutUri: values.NEXT_PUBLIC_COGNITO_LOGOUT_URI!,
    scope: values.NEXT_PUBLIC_COGNITO_SCOPE!,
    cognitoDomain: values.NEXT_PUBLIC_COGNITO_DOMAIN!,
  };
}
