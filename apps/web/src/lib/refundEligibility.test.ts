import { describe, expect, it } from "vitest";
import type { components } from "@copilot/api-client";
import { getRefundIneligibilityReason, REFUND_WINDOW_DAYS } from "./refundEligibility";

type Order = components["schemas"]["OrderResponse"];

function makeOrder(overrides: Partial<Order> = {}): Order {
  return {
    id: "order-1",
    buyer_ref: "BUYER-1",
    status: "delivered",
    total_cents: 1000,
    currency: "USD",
    placed_at: new Date().toISOString(),
    delivered_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    items: [],
    ...overrides,
  };
}

function daysAgo(days: number): string {
  return new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
}

describe("getRefundIneligibilityReason", () => {
  it("is eligible when delivered within the window", () => {
    const order = makeOrder({ status: "delivered", delivered_at: daysAgo(1) });
    expect(getRefundIneligibilityReason(order)).toBeNull();
  });

  it("is eligible exactly at the window boundary", () => {
    const order = makeOrder({ status: "delivered", delivered_at: daysAgo(REFUND_WINDOW_DAYS) });
    expect(getRefundIneligibilityReason(order)).toBeNull();
  });

  it("is ineligible when delivered outside the window", () => {
    const order = makeOrder({ status: "delivered", delivered_at: daysAgo(REFUND_WINDOW_DAYS + 5) });
    expect(getRefundIneligibilityReason(order)).toMatch(/outside the refund window/i);
  });

  it.each(["pending", "shipped"] as const)(
    "is ineligible because it hasn't been delivered yet (%s)",
    (status) => {
      const order = makeOrder({ status, delivered_at: null });
      expect(getRefundIneligibilityReason(order)).toMatch(/hasn't been delivered yet/i);
    },
  );

  it("is ineligible because it was cancelled", () => {
    const order = makeOrder({ status: "cancelled", delivered_at: null });
    expect(getRefundIneligibilityReason(order)).toMatch(/was cancelled/i);
  });

  it("is ineligible because a refund was already requested", () => {
    const order = makeOrder({ status: "refund_requested", delivered_at: daysAgo(1) });
    expect(getRefundIneligibilityReason(order)).toMatch(/already been requested/i);
  });

  it("is ineligible because it was already refunded", () => {
    const order = makeOrder({ status: "refunded", delivered_at: daysAgo(1) });
    expect(getRefundIneligibilityReason(order)).toMatch(/already been refunded/i);
  });

  it("every reason is a friendly, capitalized sentence ending in a period", () => {
    const statuses: Order["status"][] = ["pending", "shipped", "cancelled", "refund_requested", "refunded"];
    for (const status of statuses) {
      const reason = getRefundIneligibilityReason(makeOrder({ status, delivered_at: daysAgo(1) }));
      expect(reason).not.toBeNull();
      expect(reason).toMatch(/^[A-Z]/);
      expect(reason).toMatch(/\.$/);
    }
  });
});
