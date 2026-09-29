import type { User } from "oidc-client-ts";

/** Cognito puts group membership on both tokens; `.profile` is the decoded ID token. */
export function getRoles(user: User | null | undefined): string[] {
  const groups = user?.profile["cognito:groups"];
  return Array.isArray(groups) ? groups.filter((g): g is string => typeof g === "string") : [];
}

export function hasRole(user: User | null | undefined, role: string): boolean {
  return getRoles(user).includes(role);
}
