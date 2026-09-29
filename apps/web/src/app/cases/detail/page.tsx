"use client";

import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { PageHeading } from "@/components/PageHeading";
import { useCase } from "@/lib/api/hooks";
import { formatDate, formatStatus } from "@/lib/format";

function CaseDetailContent() {
  const searchParams = useSearchParams();
  const caseId = searchParams.get("id");
  const supportCase = useCase(caseId);

  if (!caseId) {
    return (
      <div>
        <PageHeading>Case not found</PageHeading>
        <p className="mt-2 text-slate-600 dark:text-slate-400">No case id was provided.</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeading>Case detail</PageHeading>
      <div aria-live="polite" className="mt-4">
        {supportCase.isLoading && <p className="text-slate-500">Loading case...</p>}
        {supportCase.isError && (
          <p role="alert" className="text-red-700 dark:text-red-400">
            {supportCase.error.message}
          </p>
        )}
        {supportCase.isSuccess && supportCase.data && (
          <dl className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 p-4 text-sm sm:grid-cols-2 dark:border-slate-800">
            <div className="sm:col-span-2">
              <dt className="text-slate-500">Description</dt>
              <dd className="font-medium">{supportCase.data.description}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Type</dt>
              <dd className="font-medium">{formatStatus(supportCase.data.type)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Status</dt>
              <dd className="font-medium">{formatStatus(supportCase.data.status)}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Opened</dt>
              <dd className="font-medium">{formatDate(supportCase.data.created_at)}</dd>
            </div>
            {supportCase.data.order_id && (
              <div>
                <dt className="text-slate-500">Order</dt>
                <dd className="font-medium">
                  <Link
                    href={`/orders/detail?id=${supportCase.data.order_id}`}
                    className="text-blue-700 underline dark:text-blue-400"
                  >
                    View order
                  </Link>
                </dd>
              </div>
            )}
          </dl>
        )}
      </div>
    </div>
  );
}

export default function CaseDetailPage() {
  return (
    <Suspense fallback={<p className="text-slate-500">Loading...</p>}>
      <CaseDetailContent />
    </Suspense>
  );
}
