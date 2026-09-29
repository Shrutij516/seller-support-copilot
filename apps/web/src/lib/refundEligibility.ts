import type { components } from "@copilot/api-client";

type Order = components["schemas"]["OrderResponse"];

// Mirrors services/api/src/copilot_api/services/refunds.py (REFUND_WINDOW_DAYS,
// request_refund's eligibility checks, and _ineligible_status_reason's wording): this is a
// client-side preview only, so the seller sees why before they submit. The server re-checks
// the same rules on submit and is the actual source of truth (clock skew, a status change
// since the page loaded, etc. can still make a client-eligible order fail server-side).
export const REFUND_WINDOW_DAYS = 30;

/** null means eligible; otherwise a friendly, sentence-case reason to show up front. */
export function getRefundIneligibilityReason(order: Order): string | null {
  if (order.status !== "delivered") {
    switch (order.status) {
      case "pending":
      case "shipped":
        return "This order hasn't been delivered yet, so it isn't eligible for a refund.";
      case "cancelled":
        return "This order was cancelled, so it isn't eligible for a refund.";
      case "refund_requested":
        return "A refund has already been requested for this order.";
      case "refunded":
        return "This order has already been refunded.";
      default:
        return "This order isn't eligible for a refund.";
    }
  }

  if (!order.delivered_at) {
    return "This order isn't eligible for a refund.";
  }

  const deliveredAt = new Date(order.delivered_at).getTime();
  const daysSinceDelivery = (Date.now() - deliveredAt) / (1000 * 60 * 60 * 24);
  if (daysSinceDelivery > REFUND_WINDOW_DAYS) {
    return `This order was delivered more than ${REFUND_WINDOW_DAYS} days ago, so it's outside the refund window.`;
  }

  return null;
}
