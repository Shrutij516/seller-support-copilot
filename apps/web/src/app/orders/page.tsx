"use client";

import { useState } from "react";
import type { components } from "@copilot/api-client";
import { PageHeading } from "@/components/PageHeading";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import { SellerOnlyNotice } from "@/components/SellerOnlyNotice";
import { StatusFilter } from "@/components/StatusFilter";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useOrdersInfinite } from "@/lib/api/hooks";
import { formatCents, formatDate, formatStatus } from "@/lib/format";

type OrderStatus = components["schemas"]["OrderStatus"];
type Order = components["schemas"]["OrderResponse"];

const ORDER_STATUSES: OrderStatus[] = [
  "pending",
  "shipped",
  "delivered",
  "cancelled",
  "refund_requested",
  "refunded",
];

const columns: Column<Order>[] = [
  { header: "Buyer", cell: (o) => o.buyer_ref },
  { header: "Status", cell: (o) => formatStatus(o.status) },
  { header: "Total", cell: (o) => formatCents(o.total_cents, o.currency) },
  { header: "Placed", cell: (o) => formatDate(o.placed_at) },
  { header: "Delivered", cell: (o) => (o.delivered_at ? formatDate(o.delivered_at) : "—") },
];

export default function OrdersPage() {
  const [status, setStatus] = useState<OrderStatus | "">("");
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");
  const orders = useOrdersInfinite(status || undefined, { enabled: !isAdmin });

  const rows = orders.data?.pages.flatMap((page) => page.items) ?? [];

  if (isAdmin) {
    return (
      <div>
        <PageHeading>Orders</PageHeading>
        <SellerOnlyNotice />
      </div>
    );
  }

  return (
    <div>
      <PageHeading>Orders</PageHeading>

      <div className="mt-4">
        <StatusFilter
          id="order-status-filter"
          label="Filter by status"
          value={status}
          statuses={ORDER_STATUSES}
          onChange={(v) => setStatus(v as OrderStatus | "")}
        />
      </div>

      <div aria-live="polite" className="mt-4">
        {orders.isLoading && <p className="text-slate-500 dark:text-slate-400">Loading orders...</p>}
        {orders.isError && (
          <p role="alert" className="text-red-700 dark:text-red-400">
            {orders.error instanceof Error ? orders.error.message : "Could not load orders."}
          </p>
        )}
        {orders.isSuccess && (
          <ResponsiveTable
            caption="Orders"
            columns={columns}
            rows={rows}
            rowKey={(o) => o.id}
            rowHref={(o) => `/orders/detail?id=${o.id}`}
            emptyMessage="No orders match this filter."
          />
        )}
      </div>

      {orders.hasNextPage && (
        <button
          type="button"
          onClick={() => void orders.fetchNextPage()}
          disabled={orders.isFetchingNextPage}
          className="mt-4 rounded-md border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          {orders.isFetchingNextPage ? "Loading more..." : "Load more"}
        </button>
      )}
    </div>
  );
}
