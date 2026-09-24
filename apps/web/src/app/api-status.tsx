"use client";

import { useCallback, useEffect, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;
const TIMEOUT_MS = 5000;

type State =
  | { kind: "loading" }
  | { kind: "ok"; requestId: string | null }
  | { kind: "error"; message: string };

async function fetchHealth(signal: AbortSignal): Promise<State> {
  if (!API_BASE_URL) {
    return { kind: "error", message: "NEXT_PUBLIC_API_BASE_URL is not set." };
  }
  try {
    const res = await fetch(`${API_BASE_URL}/healthz`, { signal, cache: "no-store" });
    if (!res.ok) {
      return { kind: "error", message: `API responded with HTTP ${res.status}.` };
    }
    const body = (await res.json()) as { status?: unknown };
    if (body.status !== "ok") {
      return { kind: "error", message: "API reported an unexpected status." };
    }
    return { kind: "ok", requestId: res.headers.get("X-Request-ID") };
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError") {
      return { kind: "error", message: `API did not respond within ${TIMEOUT_MS / 1000}s.` };
    }
    return { kind: "error", message: "Could not reach the API." };
  }
}

export function ApiStatus() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    fetchHealth(AbortSignal.timeout(TIMEOUT_MS)).then((next) => {
      if (active) setState(next);
    });
    return () => {
      active = false;
    };
  }, [attempt]);

  const retry = useCallback(() => {
    setState({ kind: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  return (
    <section className="card" aria-live="polite">
      <h2>API status</h2>
      {state.kind === "loading" && <p className="muted">Checking API health...</p>}
      {state.kind === "ok" && (
        <p className="ok">
          Healthy
          {state.requestId && <span className="muted"> (request {state.requestId})</span>}
        </p>
      )}
      {state.kind === "error" && (
        <>
          <p className="err" role="alert">
            Unavailable: {state.message}
          </p>
          <button type="button" onClick={retry}>
            Retry
          </button>
        </>
      )}
    </section>
  );
}
