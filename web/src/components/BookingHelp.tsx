import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button, Card, EmergencyButton, Textarea, showToast } from "./ui";
import { ApiError, apiFetch } from "../lib/api";

// The Emergency and Issues buttons on a booking (CLAUDE.md 6.9), for parents and sitters: from the start
// until 1 hour after the end or check-out (the API's `buttons_open`).
// - Emergency: every admin is told at once. Parents pick Emergency, Theft or Abuse (theft or abuse suspends
//   the sitter until Pacifyco looks into it); sitters pick Emergency or "I'm being abused or feel unsafe".
// - Issues: a non-emergency issue (running late, something else) for Pacifyco to follow up.

export type BookingIncident = { kind: string; status: "open" | "acknowledged" | "resolved"; created_at: string };

type Role = "parent" | "sitter";

const KINDS: Record<Role, [string, string][]> = {
  parent: [
    ["emergency", "An emergency (safety or medical)"],
    ["theft", "Something has been stolen"],
    ["abuse", "My child has been hurt or mistreated"],
  ],
  sitter: [
    ["emergency", "An emergency (safety or medical)"],
    ["sitter_unsafe", "I'm being abused or I feel unsafe"],
  ],
};

const TOPICS: [string, string][] = [
  ["running_late", "Running late"],
  ["other", "Something else"],
];

function Radios({
  name,
  legend,
  options,
  value,
  onChange,
  inverse = false,
}: {
  name: string;
  legend: string;
  options: [string, string][];
  value: string;
  onChange: (value: string) => void;
  inverse?: boolean;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className={inverse ? "text-ui" : "text-ui text-ink"}>{legend}</legend>
      {options.map(([option, label]) => (
        <label key={option} className="flex cursor-pointer items-center gap-3 text-body">
          <input
            type="radio"
            name={name}
            value={option}
            checked={value === option}
            onChange={() => onChange(option)}
            className="size-5 cursor-pointer accent-[var(--accent-coral)]"
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}

function Emergency({ role, bookingId, queryKey }: { role: Role; bookingId: string; queryKey: unknown[] }) {
  const queryClient = useQueryClient();
  const [kind, setKind] = useState("emergency");
  const [note, setNote] = useState("");
  const send = useMutation({
    mutationFn: () =>
      apiFetch<unknown>(`/${role}/bookings/${bookingId}/emergency`, {
        method: "POST",
        body: JSON.stringify({ kind, note: note.trim() || null }),
      }),
    onSuccess: (updated) => queryClient.setQueryData(queryKey, updated),
  });
  return (
    <div className="flex flex-col gap-2">
      <EmergencyButton onConfirm={() => send.mutate()} sending={send.isPending}>
        <Radios name="emergency-kind" legend="What's happening?" options={KINDS[role]} value={kind} onChange={setKind} inverse />
        <label className="flex flex-col gap-1 text-small">
          A few words, if you can (optional)
          <textarea
            rows={2}
            maxLength={1000}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            className="rounded-md p-2 text-body text-ink"
          />
        </label>
      </EmergencyButton>
      {send.isError && (
        <p role="alert" className="text-small text-danger">
          That didn't go through. Please call Pacifyco on +91 8848873841, and 112 if anyone is in danger.
        </p>
      )}
    </div>
  );
}

function Issue({ role, bookingId }: { role: Role; bookingId: string }) {
  const [open, setOpen] = useState(false);
  const [topic, setTopic] = useState("running_late");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | undefined>();
  const send = useMutation({
    mutationFn: () =>
      apiFetch<unknown>(`/${role}/bookings/${bookingId}/issues`, {
        method: "POST",
        body: JSON.stringify({ topic, note: note.trim() || null }),
      }),
    onSuccess: () => {
      showToast("Thank you. Pacifyco will be in touch.");
      setOpen(false);
      setNote("");
    },
    onError: (failed) => setError(failed instanceof ApiError ? failed.message : "That didn't go through. Please try again."),
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (topic === "other" && !note.trim()) return setError("Please tell us what's wrong.");
    setError(undefined);
    send.mutate();
  }
  if (!open) {
    return (
      <div>
        <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setOpen(true)}>
          Report an issue
        </Button>
      </div>
    );
  }
  return (
    <Card as="section" padding="roomy">
      <form noValidate onSubmit={submit} className="flex flex-col gap-3">
        <Radios name="issue-topic" legend="Not an emergency? Tell Pacifyco." options={TOPICS} value={topic} onChange={setTopic} />
        {role === "sitter" && (
          <p className="text-small text-muted">If the only adult at home is a man, use "Only a man is at home" instead.</p>
        )}
        <Textarea
          label="What's happening?"
          optional={topic !== "other"}
          rows={2}
          maxLength={1000}
          value={note}
          error={error}
          onChange={(event) => setNote(event.target.value)}
        />
        <div className="flex flex-wrap gap-3">
          <Button type="submit" variant="secondary" loading={send.isPending}>
            Send to Pacifyco
          </Button>
          <Button variant="tertiary" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** Emergency and Issues for a booking, while they're open; and whether an emergency has been raised. */
export function BookingHelp({
  role,
  bookingId,
  buttonsOpen,
  incident,
  queryKey,
}: {
  role: Role;
  bookingId: string;
  buttonsOpen: boolean;
  incident: BookingIncident | null;
  queryKey: unknown[];
}) {
  const raised = incident && incident.status !== "resolved";
  if (!buttonsOpen && !raised) return null;
  return (
    <div className="flex flex-col gap-3">
      {raised && (
        <Card as="section" padding="roomy" role="status" className="border-l-4 border-coral">
          <p className="text-ink">
            {incident.status === "acknowledged"
              ? "Pacifyco is dealing with the emergency you reported and will call you."
              : "Pacifyco has been alerted and will call you. If anyone is in danger, call 112."}
          </p>
        </Card>
      )}
      {buttonsOpen && !raised && <Emergency role={role} bookingId={bookingId} queryKey={queryKey} />}
      {buttonsOpen && <Issue role={role} bookingId={bookingId} />}
    </div>
  );
}
