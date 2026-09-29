/** RFC 9457 (application/problem+json) shape every error response uses. */
export interface ProblemDetail {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  request_id?: string;
}

export function isProblemDetail(value: unknown): value is ProblemDetail {
  return typeof value === "object" && value !== null && ("title" in value || "status" in value);
}

const STATUS_MESSAGES: Record<number, string> = {
  401: "Your session has expired. Please sign in again.",
  403: "You don't have access to do that.",
  404: "That item couldn't be found.",
  409: "This conflicts with the current state.",
  422: "Please check the form and try again.",
  500: "Something went wrong on our end. Please try again.",
};

/**
 * A message safe to show a user: prefers the server's own `detail` (already written to be
 * shown, per the API's error-handling design), falls back to a generic per-status message,
 * then a generic fallback. Never shows `type`, raw status codes, or anything else internal.
 */
export function friendlyMessage(
  problem: ProblemDetail | null | undefined,
  fallback = "Something went wrong. Please try again.",
): string {
  if (!problem) return fallback;
  if (problem.detail) return problem.detail;
  const statusMessage = problem.status ? STATUS_MESSAGES[problem.status] : undefined;
  if (statusMessage) return statusMessage;
  if (problem.title) return problem.title;
  return fallback;
}
