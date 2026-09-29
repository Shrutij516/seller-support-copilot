"use client";

import { createApiClient, type ApiClient, type Middleware } from "@copilot/api-client";
import { getUserManager } from "../auth/userManager";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

function authMiddleware(): Middleware {
  return {
    async onRequest({ request }) {
      const userManager = getUserManager();
      const user = await userManager.getUser();
      if (user && !user.expired) {
        request.headers.set("Authorization", `Bearer ${user.access_token}`);
      }
      return request;
    },
  };
}

let client: ApiClient | null = null;

/** One client per browser session, auth header attached per-request (not baked in at
 * creation), since the access token can change (sign-in) after the client is built.
 */
export function getApiClient(): ApiClient {
  client ??= createApiClient(API_BASE_URL, [authMiddleware()]);
  return client;
}
