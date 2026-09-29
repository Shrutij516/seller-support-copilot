import { UserManager, WebStorageStateStore } from "oidc-client-ts";
import { loadAuthConfig } from "./config";

let instance: UserManager | null = null;

/**
 * Lazily constructed, browser-only (touches sessionStorage). Never call this at module
 * top-level or during the initial render of a "use client" component: static export still
 * renders once in Node at build time, and window/sessionStorage don't exist there. Call it
 * from inside useEffect or an event handler instead.
 */
export function getUserManager(): UserManager {
  if (!instance) {
    const config = loadAuthConfig();
    instance = new UserManager({
      authority: config.authority,
      client_id: config.clientId,
      redirect_uri: config.redirectUri,
      response_type: "code",
      scope: config.scope,
      // sessionStorage, not localStorage: tokens die with the tab. See DECISIONS.md
      // "Token storage: sessionStorage" for the XSS tradeoff this accepts.
      userStore: new WebStorageStateStore({ store: window.sessionStorage }),
      automaticSilentRenew: false,
    });
  }
  return instance;
}

/**
 * Cognito's hosted-UI logout isn't part of standard OIDC discovery (no end_session_endpoint
 * is published), so this is built by hand from the documented /logout contract instead of
 * something oidc-client-ts can discover on its own.
 */
export function buildCognitoLogoutUrl(): string {
  const config = loadAuthConfig();
  const params = new URLSearchParams({
    client_id: config.clientId,
    logout_uri: config.logoutUri,
  });
  return `${config.cognitoDomain}/logout?${params.toString()}`;
}
