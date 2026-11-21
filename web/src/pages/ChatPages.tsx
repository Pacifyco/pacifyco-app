import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";
import { BackLink, Button, ButtonLink, Card, EmptyState } from "../components/ui";
import { cx } from "../components/ui/cx";
import { ApiError, apiFetch } from "../lib/api";
import { formatDay, formatTime } from "../lib/format";

// Chat between a parent and a sitter (CLAUDE.md 6.11). It opens once they have a confirmed booking; new
// messages can be sent while they have a booking now or to come, and for 24 hours after their last one
// (Reuben, 2026-11-21). The open chat asks for new messages every 10 seconds (no websockets).

export type ChatMessage = { id: string; from_me: boolean; body: string; created_at: string };
export type Chat = { other_id: string; other_name: string | null; can_send: boolean; messages: ChatMessage[] };
export type ChatSummary = {
  other_id: string;
  other_name: string | null;
  last_body: string | null;
  last_at: string | null;
  last_from_me: boolean;
  can_send: boolean;
};

type Role = "parent" | "sitter";

const POLL_MS = 10_000;

function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

export function ChatsPage({ role }: { role: Role }) {
  const chats = useQuery({
    queryKey: [role, "chats"],
    queryFn: () => apiFetch<ChatSummary[]>(`/${role}/chats`),
    refetchInterval: POLL_MS,
  });
  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-4">
      <h1>Messages</h1>
      {chats.isPending && <p className="text-center text-muted">Loading…</p>}
      {chats.isError && (
        <p role="alert" className="text-danger">
          We couldn't load your messages. Please try again.
        </p>
      )}
      {chats.isSuccess &&
        (chats.data.length === 0 ? (
          <EmptyState
            message={
              role === "parent"
                ? "No messages yet. You can message a sitter once you have a confirmed booking with her."
                : "No messages yet. You can message a family once you have a confirmed booking with them."
            }
            action={role === "parent" ? <ButtonLink to="/parent/bookings">Your bookings</ButtonLink> : undefined}
          />
        ) : (
          <Card as="section" padding="roomy">
            <ul>
              {chats.data.map((chat) => (
                <li key={chat.other_id} className="border-t border-line first:border-t-0">
                  <Link to={`/${role}/chats/${chat.other_id}`} className="flex items-center gap-4 py-4 text-ink no-underline">
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="text-ui">{chat.other_name ?? "Chat"}</span>
                      <span className="truncate text-small text-muted">
                        {chat.last_body ? `${chat.last_from_me ? "You: " : ""}${chat.last_body}` : "No messages yet"}
                      </span>
                    </span>
                    <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}

export function ChatPage({ role }: { role: Role }) {
  const { otherId = "" } = useParams();
  const queryClient = useQueryClient();
  const key = [role, "chat", otherId];
  const chat = useQuery({
    queryKey: key,
    queryFn: () => apiFetch<Chat>(`/${role}/chats/${otherId}`),
    refetchInterval: POLL_MS,
  });
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: (text: string) =>
      apiFetch<Chat>(`/${role}/chats/${otherId}`, { method: "POST", body: JSON.stringify({ body: text }) }),
    onSuccess: (updated) => {
      queryClient.setQueryData(key, updated);
      setBody("");
    },
    onError: (failed) => setError(failed instanceof ApiError ? failed.message : "That didn't send. Please try again."),
  });
  const end = useRef<HTMLDivElement>(null);
  const count = chat.data?.messages.length ?? 0;
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [count]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!body.trim()) return;
    setError(null);
    send.mutate(body.trim());
  }

  const back = <BackLink to={`/${role}/chats`} label="Messages" />;
  if (chat.isPending) return <p className="text-center text-muted">Loading…</p>;
  if (chat.isError) {
    return (
      <section className="mx-auto flex max-w-[62ch] flex-col gap-4">
        {back}
        <EmptyState message="You can message each other once you have a confirmed booking together." />
      </section>
    );
  }
  const data = chat.data;
  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-4">
      {back}
      <h1>{data.other_name ?? "Chat"}</h1>
      <Card as="section" padding="roomy" aria-label="Messages" className="flex flex-col gap-3">
        {data.messages.length === 0 ? (
          <p className="text-muted">No messages yet. Say hello.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {data.messages.map((message) => (
              <li key={message.id} className={cx("flex flex-col gap-1", message.from_me ? "items-end" : "items-start")}>
                <p
                  className={cx(
                    "max-w-[85%] rounded-lg px-4 py-2 whitespace-pre-wrap",
                    message.from_me ? "bg-coral text-on-coral" : "bg-surface-sunken text-ink",
                  )}
                >
                  {message.body}
                </p>
                <span className="text-small text-muted">{when(message.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
        <div ref={end} />
      </Card>
      {data.can_send ? (
        <form noValidate onSubmit={submit} className="flex flex-col gap-2">
          <label className="flex flex-col gap-1 text-small text-ink">
            Your message
            <textarea
              rows={2}
              maxLength={2000}
              value={body}
              onChange={(event) => setBody(event.target.value)}
              className="rounded-md border border-strong bg-surface-raised p-3 text-body text-ink"
            />
          </label>
          {error && (
            <p role="alert" className="text-small text-danger">
              {error}
            </p>
          )}
          <div>
            <Button type="submit" loading={send.isPending} disabled={!body.trim()}>
              Send
            </Button>
          </div>
          {role === "sitter" && <p className="text-small text-muted">You never have to share your phone number.</p>}
        </form>
      ) : (
        <p className="text-muted">This chat is closed. It opens again when you have another booking together.</p>
      )}
    </section>
  );
}
