"use client";

import { useEffect, useRef, type ReactNode } from "react";

/** Focus moves here on every route change: each page mounts a fresh instance, so a
 * mount-time focus is exactly "focus moved to the main heading on route change." */
export function PageHeading({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  return (
    <h1 ref={ref} tabIndex={-1} className="text-2xl font-semibold tracking-tight outline-none">
      {children}
    </h1>
  );
}
