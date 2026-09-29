import Link from "next/link";

/** Shown instead of seller-scoped content (orders, cases, chat, dashboard) when an admin
 * opens one of those pages directly: the nav already hides links to them for admins, this is
 * the fallback for a typed-in URL. Admin routes are role-gated server-side too (require_role
 * "admin"), but this page's own data hooks are seller-only, so nothing here ever calls them.
 */
export function SellerOnlyNotice() {
  return (
    <p
      role="status"
      className="mt-4 rounded-md border border-slate-300 bg-slate-50 p-4 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
    >
      This page is for sellers. As an admin, you can review cases at{" "}
      <Link href="/admin/cases" className="underline">
        Admin: cases
      </Link>
      .
    </p>
  );
}
