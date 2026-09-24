import { ApiStatus } from "./api-status";

export default function Home() {
  return (
    <main>
      <h1>Seller Support Copilot</h1>
      <p className="muted">AI support for e-commerce sellers: policies, orders, and listings.</p>
      <ApiStatus />
    </main>
  );
}
