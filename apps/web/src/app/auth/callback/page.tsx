"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { getUserManager } from "@/lib/auth/userManager";
import { PageHeading } from "@/components/PageHeading";

export default function AuthCallbackPage() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getUserManager()
      .signinCallback()
      .then(() => {
        router.replace("/");
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Sign-in failed. Please try again.");
      });
  }, [router]);

  return (
    <div>
      <PageHeading>Signing you in</PageHeading>
      <div aria-live="polite" className="mt-4">
        {error ? (
          <div
            role="alert"
            className="rounded-md border border-red-300 bg-red-50 p-4 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100"
          >
            <p className="font-semibold">Sign-in failed</p>
            <p className="mt-1 text-sm">{error}</p>
            <Link href="/" className="mt-3 inline-block underline">
              Return to the dashboard
            </Link>
          </div>
        ) : (
          <p className="text-slate-600 dark:text-slate-400">Please wait...</p>
        )}
      </div>
    </div>
  );
}
