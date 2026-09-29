"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth/AuthProvider";

const SELLER_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/orders", label: "Orders" },
  { href: "/cases", label: "Cases" },
  { href: "/chat", label: "Chat" },
];

function NavLink({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href;
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`rounded-md px-3 py-2 text-sm font-medium ${
        active
          ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
          : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      }`}
    >
      {label}
    </Link>
  );
}

export function NavShell({ children }: { children: React.ReactNode }) {
  const { user, roles, isLoading, configError, signIn, signOut } = useAuth();
  const isAdmin = roles.includes("admin");

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:m-2 focus:rounded focus:bg-blue-600 focus:px-4 focus:py-2 focus:text-white"
      >
        Skip to main content
      </a>
      <header className="border-b border-slate-200 dark:border-slate-800">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <span className="text-lg font-semibold">Seller Support Copilot</span>
          <nav aria-label="Primary" className="flex flex-wrap items-center gap-1">
            {isAdmin
              ? <NavLink href="/admin/cases" label="Admin" />
              : SELLER_LINKS.map((link) => (
                  <NavLink key={link.href} href={link.href} label={link.label} />
                ))}
          </nav>
          <div className="flex items-center gap-3">
            {!isLoading && !configError && user && (
              <span className="hidden text-sm text-slate-600 sm:inline dark:text-slate-400">
                {user.profile.email ?? "Signed in"}
              </span>
            )}
            {!isLoading && !configError && (
              <button
                type="button"
                onClick={user ? signOut : signIn}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
              >
                {user ? "Sign out" : "Sign in"}
              </button>
            )}
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        {configError ? (
          <div
            role="alert"
            className="rounded-md border border-red-300 bg-red-50 p-4 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100"
          >
            <p className="font-semibold">Authentication is not configured</p>
            <p className="mt-1 text-sm">{configError}</p>
          </div>
        ) : (
          children
        )}
      </main>
    </div>
  );
}
