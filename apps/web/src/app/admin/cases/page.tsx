"use client";

import { useState } from "react";
import type { components } from "@copilot/api-client";
import { PageHeading } from "@/components/PageHeading";
import { StatusFilter } from "@/components/StatusFilter";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useAdminCases, useUpdateAdminCase } from "@/lib/api/hooks";
import { formatDate, formatStatus } from "@/lib/format";

type CaseStatus = components["schemas"]["CaseStatus"];

const CASE_STATUSES: CaseStatus[] = ["open", "in_progress", "resolved"];

// Mirrors the API's allowed-transition table (services/api ALLOWED_CASE_TRANSITIONS) so the
// UI only offers buttons the backend will actually accept. The backend still enforces this;
// this is only here so a seller doesn't click a button that's guaranteed to 409.
const NEXT_STATUS: Record<CaseStatus, CaseStatus | null> = {
  open: "in_progress",
  in_progress: "resolved",
  resolved: null,
};

function TransitionButton({ caseId, status }: { caseId: string; status: CaseStatus }) {
  const mutation = useUpdateAdminCase();
  const next = NEXT_STATUS[status];

  if (!next) {
    return <span className="text-sm text-slate-400">No further action</span>;
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => mutation.mutate({ caseId, status: next })}
        disabled={mutation.isPending}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800"
      >
        {mutation.isPending ? "Updating..." : `Mark ${formatStatus(next)}`}
      </button>
      {mutation.isError && (
        <p role="alert" className="mt-1 text-xs text-red-700 dark:text-red-400">
          {mutation.error.message}
        </p>
      )}
    </div>
  );
}

function AdminCasesList() {
  const [status, setStatus] = useState<CaseStatus | "">("");
  const cases = useAdminCases(status || undefined);
  const rows = cases.data?.items ?? [];

  return (
    <div>
      <div className="mt-4">
        <StatusFilter
          id="admin-case-status-filter"
          label="Filter by status"
          value={status}
          statuses={CASE_STATUSES}
          onChange={(v) => setStatus(v as CaseStatus | "")}
        />
      </div>

      <div aria-live="polite" className="mt-4">
        {cases.isLoading && <p className="text-slate-500">Loading cases...</p>}
        {cases.isError && (
          <p role="alert" className="text-red-700 dark:text-red-400">
            {cases.error.message}
          </p>
        )}
        {cases.isSuccess && rows.length === 0 && <p className="text-slate-500">No cases match this filter.</p>}

        {rows.length > 0 && (
          <ul className="mt-2 space-y-3">
            {rows.map((c) => (
              <li
                key={c.id}
                className="flex flex-col gap-2 rounded-lg border border-slate-200 p-3 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800"
              >
                <div>
                  <p className="font-medium">{c.description}</p>
                  <p className="text-sm text-slate-500">
                    {formatStatus(c.type)} &middot; {formatStatus(c.status)} &middot; opened{" "}
                    {formatDate(c.created_at)}
                  </p>
                </div>
                <TransitionButton caseId={c.id} status={c.status} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function AdminCasesPage() {
  const { user, roles, isLoading } = useAuth();
  const isAdmin = roles.includes("admin");

  return (
    <div>
      <PageHeading>Admin: cases</PageHeading>

      {isLoading && <p className="mt-4 text-slate-500">Loading...</p>}

      {!isLoading && !user && (
        <p className="mt-4 text-slate-600 dark:text-slate-400">Sign in to continue.</p>
      )}

      {!isLoading && user && !isAdmin && (
        <div
          role="alert"
          className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-4 text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
        >
          This page is only available to admins. If you believe this is a mistake, the API
          will still reject any request you make here.
        </div>
      )}

      {!isLoading && user && isAdmin && <AdminCasesList />}
    </div>
  );
}
