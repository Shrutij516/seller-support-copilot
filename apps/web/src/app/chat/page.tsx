"use client";

import { useState, type FormEvent } from "react";
import { PageHeading } from "@/components/PageHeading";
import { SellerOnlyNotice } from "@/components/SellerOnlyNotice";
import { useAuth } from "@/lib/auth/AuthProvider";
import { ChatThread } from "@/components/chat/ChatThread";
import { useChatSessions, useCreateChatSession } from "@/lib/api/hooks";

function NewSessionForm({ onCreated }: { onCreated: (sessionId: string) => void }) {
  const [title, setTitle] = useState("");
  const mutation = useCreateChatSession();

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    mutation.mutate(title, {
      onSuccess: (session) => {
        setTitle("");
        onCreated(session.session_id);
      },
    });
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <label htmlFor="new-session-title" className="sr-only">
        New session title
      </label>
      <input
        id="new-session-title"
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="What's this about?"
        maxLength={200}
        className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900"
      />
      <button
        type="submit"
        disabled={mutation.isPending || !title.trim()}
        className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {mutation.isPending ? "Starting..." : "New session"}
      </button>
      {mutation.isError && (
        <p role="alert" className="sr-only">
          {mutation.error.message}
        </p>
      )}
    </form>
  );
}

export default function ChatPage() {
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");
  const sessions = useChatSessions({ enabled: !isAdmin });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const sessionList = sessions.data?.items ?? [];
  const activeId = selectedId ?? sessionList[0]?.session_id ?? null;

  if (isAdmin) {
    return (
      <div>
        <PageHeading>Chat</PageHeading>
        <SellerOnlyNotice />
      </div>
    );
  }

  return (
    <div>
      <PageHeading>Chat</PageHeading>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Answers come only from the marketplace policies, with their sources listed under each answer.
      </p>

      <div className="mt-4">
        <NewSessionForm onCreated={setSelectedId} />
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-[16rem_1fr]">
        <section aria-labelledby="chat-sessions-heading">
          <h2 id="chat-sessions-heading" className="text-sm font-semibold text-slate-500 dark:text-slate-400">
            Sessions
          </h2>
          <div aria-live="polite" className="mt-2">
            {sessions.isLoading && <p className="text-slate-500 dark:text-slate-400">Loading sessions...</p>}
            {sessions.isError && (
              <p role="alert" className="text-red-700 dark:text-red-400">
                {sessions.error.message}
              </p>
            )}
            {sessions.isSuccess && sessionList.length === 0 && (
              <p className="text-slate-500 dark:text-slate-400">No sessions yet.</p>
            )}
            {sessionList.length > 0 && (
              <ul className="space-y-1">
                {sessionList.map((session) => (
                  <li key={session.session_id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(session.session_id)}
                      aria-current={session.session_id === activeId ? "true" : undefined}
                      className={`w-full rounded-md px-2 py-1.5 text-left text-sm ${
                        session.session_id === activeId
                          ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                          : "hover:bg-slate-100 dark:hover:bg-slate-800"
                      }`}
                    >
                      {session.title}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section aria-labelledby="chat-messages-heading">
          <h2 id="chat-messages-heading" className="text-sm font-semibold text-slate-500 dark:text-slate-400">
            Messages
          </h2>
          {activeId ? (
            <ChatThread key={activeId} sessionId={activeId} />
          ) : (
            <p className="mt-2 text-slate-500 dark:text-slate-400">Select or start a session.</p>
          )}
        </section>
      </div>
    </div>
  );
}
