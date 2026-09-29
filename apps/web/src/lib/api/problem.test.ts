import { describe, expect, it } from "vitest";
import { friendlyMessage, isProblemDetail } from "./problem";
import { ApiError } from "./errors";

describe("isProblemDetail", () => {
  it("accepts an object with a title", () => {
    expect(isProblemDetail({ title: "Not Found" })).toBe(true);
  });

  it("accepts an object with a status", () => {
    expect(isProblemDetail({ status: 404 })).toBe(true);
  });

  it("rejects null, primitives, and plain objects without title/status", () => {
    expect(isProblemDetail(null)).toBe(false);
    expect(isProblemDetail(undefined)).toBe(false);
    expect(isProblemDetail("error")).toBe(false);
    expect(isProblemDetail({ message: "oops" })).toBe(false);
  });
});

describe("friendlyMessage", () => {
  it("prefers the server-provided detail", () => {
    expect(friendlyMessage({ status: 422, detail: "Reason is too short." })).toBe(
      "Reason is too short.",
    );
  });

  it("falls back to the per-status message when there is no detail", () => {
    expect(friendlyMessage({ status: 401 })).toMatch(/session has expired/i);
    expect(friendlyMessage({ status: 403 })).toMatch(/don't have access/i);
    expect(friendlyMessage({ status: 404 })).toMatch(/couldn't be found/i);
    expect(friendlyMessage({ status: 409 })).toMatch(/conflicts with the current state/i);
    expect(friendlyMessage({ status: 422 })).toMatch(/check the form/i);
    expect(friendlyMessage({ status: 500 })).toMatch(/went wrong on our end/i);
  });

  it("falls back to the problem title when the status is unmapped", () => {
    expect(friendlyMessage({ status: 418, title: "I'm a teapot" })).toBe("I'm a teapot");
  });

  it("falls back to the generic fallback when nothing else is available", () => {
    expect(friendlyMessage(null)).toBe("Something went wrong. Please try again.");
    expect(friendlyMessage({})).toBe("Something went wrong. Please try again.");
  });
});

describe("ApiError", () => {
  it("parses a problem+json error body into a friendly message and exposes status", () => {
    const err = new ApiError({ status: 409, detail: "Order already refunded." });
    expect(err.message).toBe("Order already refunded.");
    expect(err.status).toBe(409);
    expect(err.problem).toEqual({ status: 409, detail: "Order already refunded." });
  });

  it("falls back to a generic message when the body is not a problem+json shape", () => {
    const err = new ApiError("network failure", 0);
    expect(err.message).toBe("Something went wrong. Please try again.");
    expect(err.problem).toBeNull();
    expect(err.status).toBe(0);
  });
});
