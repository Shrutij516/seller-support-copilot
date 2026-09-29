import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AuthProvider } from "@/lib/auth/AuthProvider";
import { QueryProvider } from "@/lib/query/QueryProvider";
import { NavShell } from "@/components/NavShell";
import { buildContentSecurityPolicy } from "./csp";
import "./globals.css";

export const metadata: Metadata = {
  title: "Seller Support Copilot",
  description: "AI support for e-commerce sellers: policies, orders, and listings.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        {/* Dev-only skip: next dev's Turbopack HMR client injects its own inline bootstrap
            scripts that change per session, so they can't be hash-pinned like the static
            export's build-time-fixed ones (see scripts/inject-csp-hashes.mjs). The policy
            only needs to hold for what actually gets deployed: the production build. */}
        {process.env.NODE_ENV === "production" && (
          <meta httpEquiv="Content-Security-Policy" content={buildContentSecurityPolicy()} />
        )}
      </head>
      <body>
        <AuthProvider>
          <QueryProvider>
            <NavShell>{children}</NavShell>
          </QueryProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
