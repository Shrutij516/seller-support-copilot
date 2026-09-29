/** Built at build time from NEXT_PUBLIC_* env vars (static export has no server to set a
 * real response header from), so this must be a <meta http-equiv> tag instead. connect-src
 * needs both the API and Cognito's two hosts: the issuer (OIDC discovery + JWKS) and the
 * hosted-UI domain (token exchange during the callback).
 */
function hostOf(url: string | undefined): string | null {
  if (!url) return null;
  try {
    return new URL(url).origin;
  } catch {
    return null;
  }
}

export function buildContentSecurityPolicy(): string {
  const connectSrc = new Set(["'self'"]);
  for (const url of [
    process.env.NEXT_PUBLIC_API_BASE_URL,
    process.env.NEXT_PUBLIC_COGNITO_AUTHORITY,
    process.env.NEXT_PUBLIC_COGNITO_DOMAIN,
  ]) {
    const host = hostOf(url);
    if (host) connectSrc.add(host);
  }

  const formAction = new Set(["'self'"]);
  const cognitoDomainHost = hostOf(process.env.NEXT_PUBLIC_COGNITO_DOMAIN);
  if (cognitoDomainHost) formAction.add(cognitoDomainHost);

  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": ["'self'"],
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:"],
    "font-src": ["'self'"],
    "connect-src": [...connectSrc],
    "form-action": [...formAction],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'none'"],
  };

  return Object.entries(directives)
    .map(([directive, sources]) => `${directive} ${sources.join(" ")}`)
    .join("; ");
}
