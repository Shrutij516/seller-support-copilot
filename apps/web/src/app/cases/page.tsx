"use client";

import type { components } from "@copilot/api-client";
import { PageHeading } from "@/components/PageHeading";
import { ResponsiveTable, type Column } from "@/components/ResponsiveTable";
import { SellerOnlyNotice } from "@/components/SellerOnlyNotice";
import { useAuth } from "@/lib/auth/AuthProvider";
import { useCases } from "@/lib/api/hooks";
import { formatDate, formatStatus } from "@/lib/format";

type SupportCase = components["schemas"]["SupportCaseResponse"];

const columns: Column<SupportCase>[] = [
  { header: "Description", cell: (c) => c.description },
  { header: "Type", cell: (c) => formatStatus(c.type) },
  { header: "Status", cell: (c) => formatStatus(c.status) },
  { header: "Opened", cell: (c) => formatDate(c.created_at) },
];

export default function CasesPage() {
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");
  const cases = useCases({ enabled: !isAdmin });
  const rows = cases.data?.items ?? [];

  if (isAdmin) {
    return (
      <div>
        <PageHeading>Cases</PageHeading>
        <SellerOnlyNotice />
      </div>
    );
  }

  return (
    <div>
      <PageHeading>Cases</PageHeading>

      <div aria-live="polite" className="mt-4">
        {cases.isLoading && <p className="text-slate-500 dark:text-slate-400">Loading cases...</p>}
        {cases.isError && (
          <p role="alert" className="text-red-700 dark:text-red-400">
            {cases.error.message}
          </p>
        )}
        {cases.isSuccess && (
          <ResponsiveTable
            caption="Support cases"
            columns={columns}
            rows={rows}
            rowKey={(c) => c.id}
            rowHref={(c) => `/cases/detail?id=${c.id}`}
            emptyMessage="No cases yet."
          />
        )}
      </div>
    </div>
  );
}
