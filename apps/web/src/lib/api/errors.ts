import { friendlyMessage, isProblemDetail, type ProblemDetail } from "./problem";

/** Wraps whatever openapi-fetch's `error` field held into a normal Error with a
 * user-friendly `.message`, plus the parsed problem+json (if it was one) for callers that
 * need to branch on `.status` (the refund form does, for 409 vs 422).
 */
export class ApiError extends Error {
  readonly problem: ProblemDetail | null;
  readonly status: number | undefined;

  constructor(rawError: unknown, fallbackStatus?: number) {
    const problem = isProblemDetail(rawError) ? rawError : null;
    super(friendlyMessage(problem));
    this.name = "ApiError";
    this.problem = problem;
    this.status = problem?.status ?? fallbackStatus;
  }
}
