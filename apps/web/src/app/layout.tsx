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
        <meta httpEquiv="Content-Security-Policy" content={buildContentSecurityPolicy()} />
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
