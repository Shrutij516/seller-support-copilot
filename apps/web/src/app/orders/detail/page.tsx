"use client";

import { Suspense, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { PageHeading } from "@/components/PageHeading";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useCreateRefundRequest, useOrder } from "@/lib/api/hooks";
import { formatCents, formatDate, formatStatus } from "@/lib/format";
import { getRefundIneligibilityReason } from "@/lib/refundEligibility";

const REASON_MIN = 10;
const REASON_MAX = 1000;

function validateReason(value: string): string | null {
  if (value.trim().length < REASON_MIN) {
    return `Reason must be at least ${REASON_MIN} characters.`;
  }
  if (value.length > REASON_MAX) {
    return `Reason must be at most ${REASON_MAX} characters.`;
  }
  return null;
}

export function RefundForm({
  orderId,
  ineligibleReason,
}: {
  orderId: string;
  ineligibleReason: string | null;
}) {
  const [reason, setReason] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const mutation = useCreateRefundRequest(orderId);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (ineligibleReason) return;
    const err = validateReason(reason);
    setValidationError(err);
    if (err) return;
    mutation.mutate(reason);
  };

  if (mutation.isSuccess) {
    return (
      <div
        role="status"
        className="rounded-md border border-green-300 bg-green-50 p-4 text-green-900 dark:border-green-800 dark:bg-green-950 dark:text-green-100"
      >
        Refund request submitted.
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="mt-2 max-w-md space-y-3">
      {/* Shown up front, before the (disabled) form, so the seller sees why without having
          to try submitting first. The server re-checks eligibility on submit regardless. */}
      {ineligibleReason && (
        <p role="status" className="text-sm text-slate-600 dark:text-slate-400">
          {ineligibleReason}
        </p>
      )}
      <fieldset disabled={Boolean(ineligibleReason) || mutation.isPending} className="space-y-3">
        <div>
          <label htmlFor="refund-reason" className="block text-sm font-medium">
            Reason for refund
          </label>
          <textarea
            id="refund-reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={4}
            minLength={REASON_MIN}
            maxLength={REASON_MAX}
            aria-describedby="refund-reason-hint"
            aria-invalid={Boolean(validationError)}
            aria-errormessage={validationError ? "refund-reason-error" : undefined}
            className="mt-1 w-full rounded-md border border-slate-300 p-2 text-sm disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900"
          />
          <p id="refund-reason-hint" className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {reason.length}/{REASON_MAX} characters, minimum {REASON_MIN}
          </p>
          {validationError && (
            <p
              id="refund-reason-error"
              role="alert"
              className="mt-1 text-sm text-red-700 dark:text-red-400"
            >
              {validationError}
            </p>
          )}
        </div>
        {mutation.isError && (
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            {mutation.error.message}
          </p>
        )}
        <button
          type="submit"
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {mutation.isPending ? "Submitting..." : "Request refund"}
        </button>
      </fieldset>
    </form>
  );
}

function OrderDetailContent() {
  const searchParams = useSearchParams();
  const orderId = searchParams.get("id");
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");
  // Admins can view any order (for example while working a case that references one, see
  // GET /v1/orders/{id} allowing "seller" or "admin"), but never request a refund on a
  // seller's behalf, so the refund section below is seller-only.
  const order = useOrder(orderId);

  if (!orderId) {
    return (
      <div>
        <PageHeading>Order not found</PageHeading>
        <p className="mt-2 text-slate-600 dark:text-slate-400">No order id was provided.</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeading>Order detail</PageHeading>
      <div aria-live="polite" className="mt-4">
        {order.isLoading && <p className="text-slate-500 dark:text-slate-400">Loading order...</p>}
        {order.isError && (
          <p role="alert" className="text-red-700 dark:text-red-400">
            {order.error.message}
          </p>
        )}
        {order.isSuccess && order.data && (
          <>
            <dl className="grid grid-cols-2 gap-3 rounded-lg border border-slate-200 p-4 text-sm sm:grid-cols-3 dark:border-slate-800">
              <div>
                <dt className="text-slate-500 dark:text-slate-400">Buyer</dt>
                <dd className="font-medium">{order.data.buyer_ref}</dd>
              </div>
              <div>
                <dt className="text-slate-500 dark:text-slate-400">Status</dt>
                <dd className="font-medium">{formatStatus(order.data.status)}</dd>
              </div>
              <div>
                <dt className="text-slate-500 dark:text-slate-400">Total</dt>
                <dd className="font-medium">
                  {formatCents(order.data.total_cents, order.data.currency)}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500 dark:text-slate-400">Placed</dt>
                <dd className="font-medium">{formatDate(order.data.placed_at)}</dd>
              </div>
              {order.data.delivered_at && (
                <div>
                  <dt className="text-slate-500 dark:text-slate-400">Delivered</dt>
                  <dd className="font-medium">{formatDate(order.data.delivered_at)}</dd>
                </div>
              )}
            </dl>

            {order.data.items.length > 0 && (
              <div className="mt-4">
                <h2 className="text-lg font-semibold">Items</h2>
                <ul className="mt-2 divide-y divide-slate-200 dark:divide-slate-800">
                  {order.data.items.map((item) => (
                    <li
                      key={item.listing_id}
                      className="flex items-center justify-between gap-3 py-2 text-sm"
                    >
                      <span>
                        <span className="font-medium">{item.listing_title}</span>{" "}
                        <span className="text-slate-500 dark:text-slate-400">
                          (SKU {item.listing_sku})
                        </span>
                        <span className="text-slate-500 dark:text-slate-400"> &middot; Qty {item.quantity}</span>
                      </span>
                      <span>{formatCents(item.unit_price_cents)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!isAdmin && (
              <div className="mt-6">
                <h2 className="text-lg font-semibold">Request a refund</h2>
                <RefundForm
                  orderId={order.data.id}
                  ineligibleReason={getRefundIneligibilityReason(order.data)}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function OrderDetailPage() {
  return (
    <Suspense fallback={<p className="text-slate-500 dark:text-slate-400">Loading...</p>}>
      <OrderDetailContent />
    </Suspense>
  );
}
