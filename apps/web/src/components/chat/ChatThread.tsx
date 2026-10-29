"use client";

import { useId, useState, type FormEvent, type KeyboardEvent } from "react";
import type { components } from "@copilot/api-client";
import { CHAT_MESSAGE_MAX_CHARS, useChatMessages, useSendChatMessage } from "@/lib/api/hooks";
import type { ApiError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";

type ChatMessage = components["schemas"]["ChatMessageResponse"];
type Citation = components["schemas"]["CitationResponse"];

const UNAVAILABLE_MESSAGE = "The assistant is temporarily unavailable.";
const SESSION_GONE_MESSAGE = "This chat session no longer exists. Start a new session to keep chatting.";

/** Sources behind an answer, collapsed by default; nothing at all when there are none
 * (refusals and uncited replies carry zero citations by design). */
export function Citations({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;
  return (
    <details className="mt-2 text-xs text-slate-600 dark:text-slate-400">
      <summary className="cursor-pointer select-none font-medium">
        Sources ({citations.length})
      </summary>
      <ol className="mt-1 space-y-1">
        {citations.map((citation) => (
          <li key={citation.index}>
            <span className="font-mono">[{citation.index}]</span>{" "}
            <span className="font-medium">{citation.source}</span>
            <p className="mt-0.5 text-slate-500 dark:text-slate-500">{citation.snippet}</p>
          </li>
        ))}
      </ol>
    </details>
  );
}

function MessageItem({ message }: { message: ChatMessage }) {
  const pending = message.message_id.startsWith("optimistic-");
  return (
    <li
      className={`rounded-lg border p-3 text-sm ${
        message.role === "assistant"
          ? "border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900"
          : "border-slate-200 dark:border-slate-800"
      }`}
    >
      <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
        {message.role === "assistant" ? "Assistant" : "You"}
      </p>
      <p className="mt-1 whitespace-pre-wrap">{message.content}</p>
      {message.role === "assistant" && <Citations citations={message.citations} />}
      <p className="mt-1 text-xs text-slate-400">{pending ? "Sending..." : formatDate(message.created_at)}</p>
    </li>
  );
}

function sendErrorMessage(error: ApiError): string {
  if (error.status === 503) return UNAVAILABLE_MESSAGE;
  if (error.status === 404) return SESSION_GONE_MESSAGE;
  return error.message;
}

export function ChatThread({ sessionId }: { sessionId: string }) {
  const messages = useChatMessages(sessionId);
  const send = useSendChatMessage(sessionId);
  const [draft, setDraft] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const composerId = useId();
  const hintId = useId();

  const trimmed = draft.trim();
  const tooLong = trimmed.length > CHAT_MESSAGE_MAX_CHARS;
  const canSend = trimmed.length > 0 && !tooLong && !send.isPending;
  const sendError = send.isError ? (send.error as ApiError) : null;

  const submit = () => {
    if (!canSend) return;
    send.mutate(trimmed, {
      onSuccess: (answer) => {
        setDraft("");
        setAnnouncement(`Assistant: ${answer.content}`);
      },
    });
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline; never send mid-IME composition.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const items = messages.data?.items ?? [];

  return (
    <div>
      <div className="mt-2 min-h-[8rem]">
        {messages.isLoading && <p className="text-slate-500 dark:text-slate-400">Loading messages...</p>}
        {messages.isError && (
          <p role="alert" className="text-red-700 dark:text-red-400">
            {messages.error.message}
          </p>
        )}
        {messages.isSuccess && items.length === 0 && (
          <p className="text-slate-500 dark:text-slate-400">No messages in this session yet.</p>
        )}
        {items.length > 0 && (
          <ul className="space-y-2" aria-label="Messages in this session">
            {items.map((message) => (
              <MessageItem key={message.message_id} message={message} />
            ))}
          </ul>
        )}
        {send.isPending && (
          <p role="status" className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            The assistant is answering...
          </p>
        )}
      </div>

      {/* Announces each new answer once; the list itself isn't a live region, so screen
          readers don't re-read the whole thread on every refetch. */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </div>

      {sendError && (
        <div role="alert" className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          <p>{sendErrorMessage(sendError)}</p>
          {sendError.status === 503 && (
            <button
              type="button"
              onClick={submit}
              disabled={!canSend}
              className="mt-1 rounded-md border border-red-300 px-2 py-0.5 text-xs font-medium hover:bg-red-100 disabled:opacity-50 dark:border-red-800 dark:hover:bg-red-900"
            >
              Retry
            </button>
          )}
        </div>
      )}

      <form className="mt-4" onSubmit={handleSubmit}>
        <label htmlFor={composerId} className="text-sm font-medium">
          Ask about marketplace policies
        </label>
        <textarea
          id={composerId}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          aria-describedby={hintId}
          aria-invalid={tooLong || undefined}
          className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
        />
        <div className="mt-1 flex items-center justify-between gap-2">
          <p id={hintId} className={`text-xs ${tooLong ? "text-red-700 dark:text-red-400" : "text-slate-500 dark:text-slate-400"}`}>
            {tooLong
              ? `Too long: ${trimmed.length.toLocaleString("en-US")} / ${CHAT_MESSAGE_MAX_CHARS.toLocaleString("en-US")} characters.`
              : `Enter to send, Shift+Enter for a new line. ${trimmed.length.toLocaleString("en-US")} / ${CHAT_MESSAGE_MAX_CHARS.toLocaleString("en-US")}`}
          </p>
          <button
            type="submit"
            disabled={!canSend}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {send.isPending ? "Sending..." : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}
