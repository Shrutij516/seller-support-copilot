import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { components } from "@copilot/api-client";
import { ChatThread } from "./ChatThread";
import { getApiClient } from "@/lib/api/client";

vi.mock("@/lib/api/client", () => ({ getApiClient: vi.fn() }));
const mockedGetApiClient = vi.mocked(getApiClient);

type ChatMessage = components["schemas"]["ChatMessageResponse"];
type Citation = components["schemas"]["CitationResponse"];

const SESSION = "01SESSIONAAAAAAAAAAAAAAAAA";
const QUESTION = "How long do refunds take?";

type PostOutcome =
  | { kind: "answer"; content: string; citations: Citation[] }
  | { kind: "error"; status: number };

/**
 * In-memory stand-in for the API's chat endpoints, with the real server's storage rule:
 * the question is stored before answering, so it stays stored even when answering fails
 * (503). `nextPost` decides each POST's outcome; `hold` keeps a POST pending until released.
 */
function fakeServer() {
  const stored: ChatMessage[] = [];
  const outcomes: PostOutcome[] = [];
  let release: (() => void) | null = null;
  let holdNext = false;
  const postBodies: string[] = [];
  let seq = 0;

  const message = (role: string, content: string, citations: Citation[] = []): ChatMessage => ({
    session_id: SESSION,
    message_id: `msg-${++seq}`,
    role,
    content,
    created_at: new Date().toISOString(),
    citations,
  });

  const GET = vi.fn(async (path: string) => {
    if (path === "/v1/chat/sessions/{session_id}/messages") {
      return { data: { items: [...stored], next_cursor: null }, error: undefined, response: { status: 200 } };
    }
    return { data: { items: [], next_cursor: null }, error: undefined, response: { status: 200 } };
  });

  const POST = vi.fn(async (_path: string, init: { body: { content: string } }) => {
    postBodies.push(init.body.content);
    if (holdNext) {
      holdNext = false;
      await new Promise<void>((resolve) => {
        release = resolve;
      });
    }
    const outcome = outcomes.shift() ?? { kind: "answer", content: "ok", citations: [] };
    stored.push(message("user", init.body.content));
    if (outcome.kind === "error") {
      const titles: Record<number, string> = { 503: "Service Unavailable", 404: "Not Found" };
      return {
        data: undefined,
        error: { type: "about:blank", title: titles[outcome.status], status: outcome.status },
        response: { status: outcome.status },
      };
    }
    const answer = message("assistant", outcome.content, outcome.citations);
    stored.push(answer);
    return { data: answer, error: undefined, response: { status: 201 } };
  });

  mockedGetApiClient.mockReturnValue({ GET, POST } as unknown as ReturnType<typeof getApiClient>);
  return {
    GET,
    POST,
    postBodies,
    nextPost: (outcome: PostOutcome) => outcomes.push(outcome),
    holdNextPost: () => {
      holdNext = true;
    },
    releasePost: () => release?.(),
  };
}

function renderThread() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <ChatThread sessionId={SESSION} />
    </QueryClientProvider>,
  );
  return { textarea: screen.getByLabelText("Ask about marketplace policies") };
}

const CITATIONS: Citation[] = [
  { index: 1, source: "returns-and-refunds.md", snippet: "A buyer can request a refund within 30 days of the order's delivery date." },
  { index: 3, source: "fees.md", snippet: "When an order is refunded, Kestrel Market returns the referral fee." },
];

describe("ChatThread", () => {
  beforeEach(() => {
    mockedGetApiClient.mockReset();
  });

  it("shows the question immediately and disables Send while the answer is pending", async () => {
    const server = fakeServer();
    server.holdNextPost();
    const user = userEvent.setup();
    const { textarea } = renderThread();
    await screen.findByText("No messages in this session yet.");

    await user.type(textarea, QUESTION);
    await user.keyboard("{Enter}");

    const list = await screen.findByRole("list", { name: "Messages in this session" });
    expect(within(list).getByText(QUESTION)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sending..." })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("The assistant is answering...");
    expect(server.POST).toHaveBeenCalledTimes(1);

    server.releasePost();
    await screen.findByRole("button", { name: "Send" });
  });

  it("renders the answer with its citations collapsed, and announces it", async () => {
    const server = fakeServer();
    server.nextPost({ kind: "answer", content: "You have 30 days from delivery [1]. The referral fee is returned [3].", citations: CITATIONS });
    const user = userEvent.setup();
    const { textarea } = renderThread();
    await screen.findByText("No messages in this session yet.");

    await user.type(textarea, QUESTION);
    await user.click(screen.getByRole("button", { name: "Send" }));

    // Scoped to the list: the same text is also in the live-region announcement, by design.
    const list = await screen.findByRole("list", { name: "Messages in this session" });
    expect(await within(list).findByText(/You have 30 days from delivery \[1\]/)).toBeInTheDocument();
    const summary = screen.getByText("Sources (2)");
    const details = summary.closest("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(within(details).getByText("returns-and-refunds.md")).toBeInTheDocument();
    expect(within(details).getByText("[3]")).toBeInTheDocument();
    await user.click(summary);
    expect(details).toHaveAttribute("open");

    expect(textarea).toHaveValue("");
    expect(document.querySelector('[aria-live="polite"]')).toHaveTextContent("Assistant: You have 30 days");
  });

  it("renders no citation block for an answer with zero citations", async () => {
    const server = fakeServer();
    server.nextPost({ kind: "answer", content: "I don't know based on the marketplace policies.", citations: [] });
    const user = userEvent.setup();
    const { textarea } = renderThread();
    await screen.findByText("No messages in this session yet.");

    await user.type(textarea, "What is the capital of France?{Enter}");

    expect(await screen.findByText("I don't know based on the marketplace policies.")).toBeInTheDocument();
    expect(screen.queryByText(/^Sources/)).not.toBeInTheDocument();
    expect(document.querySelector("details")).toBeNull();
  });

  it("on 503 keeps the typed question and Retry resends it", async () => {
    const server = fakeServer();
    server.nextPost({ kind: "error", status: 503 });
    server.nextPost({ kind: "answer", content: "You have 30 days from delivery [1].", citations: [CITATIONS[0]!] });
    const user = userEvent.setup();
    const { textarea } = renderThread();
    await screen.findByText("No messages in this session yet.");

    await user.type(textarea, `${QUESTION}{Enter}`);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The assistant is temporarily unavailable.");
    expect(textarea).toHaveValue(QUESTION);

    await user.click(within(alert).getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("You have 30 days from delivery [1].")).toBeInTheDocument();
    expect(server.postBodies).toEqual([QUESTION, QUESTION]);
    expect(textarea).toHaveValue("");
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("on 404 says the session is gone and offers no Retry", async () => {
    const server = fakeServer();
    server.nextPost({ kind: "error", status: 404 });
    const user = userEvent.setup();
    const { textarea } = renderThread();
    await screen.findByText("No messages in this session yet.");

    await user.type(textarea, `${QUESTION}{Enter}`);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This chat session no longer exists.");
    expect(within(alert).queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it("blocks sending empty, whitespace-only, or over-2,000-character messages", async () => {
    const server = fakeServer();
    const user = userEvent.setup();
    const { textarea } = renderThread();
    await screen.findByText("No messages in this session yet.");
    const send = screen.getByRole("button", { name: "Send" });

    expect(send).toBeDisabled();
    fireEvent.change(textarea, { target: { value: "   \n  " } });
    expect(send).toBeDisabled();

    fireEvent.change(textarea, { target: { value: "x".repeat(2001) } });
    expect(send).toBeDisabled();
    expect(textarea).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Too long: 2,001 / 2,000 characters.")).toBeInTheDocument();
    await user.click(send);
    textarea.focus();
    await user.keyboard("{Enter}");
    expect(server.POST).not.toHaveBeenCalled();

    fireEvent.change(textarea, { target: { value: "x".repeat(2000) } });
    expect(send).toBeEnabled();
  });

  it("Shift+Enter inserts a newline instead of sending", async () => {
    const server = fakeServer();
    const user = userEvent.setup();
    const { textarea } = renderThread();
    await screen.findByText("No messages in this session yet.");

    await user.type(textarea, "line one{Shift>}{Enter}{/Shift}line two");

    expect(textarea).toHaveValue("line one\nline two");
    expect(server.POST).not.toHaveBeenCalled();
  });
});
