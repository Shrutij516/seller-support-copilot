"use client";

import Link from "next/link";
import { PageHeading } from "@/components/PageHeading";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useCases, useMe, useOrdersInfinite } from "@/lib/api/hooks";
import { formatCents, formatStatus } from "@/lib/format";

export default function DashboardPage() {
  const { user, isLoading: authLoading, signIn } = useAuth();

  if (authLoading) {
    return <p className="text-slate-600 dark:text-slate-400">Loading...</p>;
  }

  if (!user) {
    return (
      <div>
        <PageHeading>Seller Support Copilot</PageHeading>
        <p className="mt-2 text-slate-600 dark:text-slate-400">
          Sign in to see your orders, cases, and chat history.
        </p>
        <button
          type="button"
          onClick={signIn}
          className="mt-4 rounded-md bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700"
        >
          Sign in
        </button>
      </div>
    );
  }

  return <Dashboard />;
}

function Dashboard() {
  const me = useMe();
  const orders = useOrdersInfinite(undefined);
  const cases = useCases();

  const recentOrders = orders.data?.pages[0]?.items.slice(0, 5) ?? [];
  const openCases = (cases.data?.items ?? []).filter((c) => c.status !== "resolved").slice(0, 5);

  return (
    <div>
      <PageHeading>Dashboard</PageHeading>
      {me.data && (
        <p className="mt-1 text-slate-600 dark:text-slate-400">
          Welcome back, {me.data.display_name ?? me.data.email ?? "seller"}.
        </p>
      )}

      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <section aria-labelledby="recent-orders-heading" className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
          <h2 id="recent-orders-heading" className="text-lg font-semibold">
            Recent orders
          </h2>
          <div aria-live="polite" className="mt-3">
            {orders.isLoading && <p className="text-slate-500 dark:text-slate-400">Loading orders...</p>}
            {orders.isError && (
              <p role="alert" className="text-red-700 dark:text-red-400">
                {orders.error instanceof Error ? orders.error.message : "Could not load orders."}
              </p>
            )}
            {orders.isSuccess && recentOrders.length === 0 && (
              <p className="text-slate-500 dark:text-slate-400">No orders yet.</p>
            )}
            {recentOrders.length > 0 && (
              <ul className="divide-y divide-slate-200 dark:divide-slate-800">
                {recentOrders.map((order) => (
                  <li key={order.id} className="py-2">
                    <Link
                      href={`/orders/detail?id=${order.id}`}
                      className="flex items-center justify-between gap-2 hover:underline"
                    >
                      <span>{order.buyer_ref}</span>
                      <span className="text-sm text-slate-500 dark:text-slate-400">{formatStatus(order.status)}</span>
                      <span className="font-medium">{formatCents(order.total_cents, order.currency)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <Link href="/orders" className="mt-3 inline-block text-sm text-blue-700 underline dark:text-blue-400">
            View all orders
          </Link>
        </section>

        <section aria-labelledby="open-cases-heading" className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
          <h2 id="open-cases-heading" className="text-lg font-semibold">
            Open cases
          </h2>
          <div aria-live="polite" className="mt-3">
            {cases.isLoading && <p className="text-slate-500 dark:text-slate-400">Loading cases...</p>}
            {cases.isError && (
              <p role="alert" className="text-red-700 dark:text-red-400">
                {cases.error instanceof Error ? cases.error.message : "Could not load cases."}
              </p>
            )}
            {cases.isSuccess && openCases.length === 0 && (
              <p className="text-slate-500 dark:text-slate-400">No open cases.</p>
            )}
            {openCases.length > 0 && (
              <ul className="divide-y divide-slate-200 dark:divide-slate-800">
                {openCases.map((supportCase) => (
                  <li key={supportCase.id} className="py-2">
                    <Link
                      href={`/cases/detail?id=${supportCase.id}`}
                      className="flex items-center justify-between gap-2 hover:underline"
                    >
                      <span className="truncate">{supportCase.description}</span>
                      <span className="text-sm text-slate-500 dark:text-slate-400">{formatStatus(supportCase.status)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <Link href="/cases" className="mt-3 inline-block text-sm text-blue-700 underline dark:text-blue-400">
            View all cases
          </Link>
        </section>
      </div>
    </div>
  );
}
