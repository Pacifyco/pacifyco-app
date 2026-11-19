import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button, Card, Textarea } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDate, formatDay, formatTime } from "../../lib/format";
import { ViewDocumentButton, errorMessage } from "./shared";

// A sitter's strikes, for admins (CLAUDE.md 6.6): the ladder blocks her from new bookings (24 hours, 3
// days, 1 week, 2 weeks; the 5th removes her). Admins give or remove a strike with a reason the sitter
// sees, both audit logged; a doctor's note she sent for a late cancellation can be viewed (logged).

export type AdminStrike = {
  id: string;
  reason: "late_cancellation" | "no_show" | "admin";
  note: string | null;
  given_at: string;
  expires_at: string;
  booking_id: string | null;
  booking_starts_at: string | null;
  removed_at: string | null;
  removal_reason: string | null;
  doctor_note_sent: boolean;
  removed_by: string | null;
  doctor_note_document_id: string | null;
};

export type AdminStrikes = { blocked_until: string | null; counting: number; strikes: AdminStrike[] };

export const REASON_WORDS: Record<AdminStrike["reason"], string> = {
  late_cancellation: "Late cancellation",
  no_show: "No-show",
  admin: "Given by an admin",
};

function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

function ReasonForm({
  label,
  submit,
  pending,
  onSubmit,
}: {
  label: string;
  submit: string;
  pending: boolean;
  onSubmit: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  function send(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) {
      setError("Please give a reason; it's shown to the sitter.");
      return;
    }
    setError(null);
    onSubmit(reason.trim());
  }
  return (
    <form noValidate onSubmit={send} className="flex flex-col gap-2">
      <Textarea label={label} value={reason} onChange={(event) => setReason(event.target.value)} error={error ?? undefined} />
      <div>
        <Button type="submit" variant="secondary" fullWidthOnPhone={false} loading={pending}>
          {submit}
        </Button>
      </div>
    </form>
  );
}

function StrikeRow({ strike, sitterId }: { strike: AdminStrike; sitterId: string }) {
  const queryClient = useQueryClient();
  const [removing, setRemoving] = useState(false);
  const remove = useMutation({
    mutationFn: (reason: string) =>
      apiFetch<AdminStrikes>(`/admin/strikes/${strike.id}/remove`, { method: "POST", body: JSON.stringify({ reason }) }),
    onSuccess: (updated) => queryClient.setQueryData(["admin", "strikes", sitterId], updated),
  });
  const expired = new Date(strike.expires_at) <= new Date();
  return (
    <li className="flex flex-col gap-2 border-t border-line py-4 first:border-t-0">
      <p className="text-ui text-ink">
        {REASON_WORDS[strike.reason]} · {when(strike.given_at)}
        {strike.removed_at ? " · removed" : expired ? " · expired" : ""}
      </p>
      {strike.booking_starts_at && <p className="text-small text-muted">Booking on {when(strike.booking_starts_at)}</p>}
      {strike.note && <p className="text-small text-ink">{strike.note}</p>}
      {strike.removed_at ? (
        <p className="text-small text-muted">
          Removed {formatDate(new Date(strike.removed_at))}: {strike.removal_reason}
        </p>
      ) : (
        <p className="text-small text-muted">Counts until {formatDate(new Date(strike.expires_at))}</p>
      )}
      {strike.doctor_note_document_id && (
        <div>
          <ViewDocumentButton
            document={{ id: strike.doctor_note_document_id, type: "doctor_note", uploaded_at: strike.given_at }}
            label="Doctor's note"
          />
        </div>
      )}
      {!strike.removed_at &&
        (removing ? (
          <ReasonForm
            label="Why remove it? The sitter sees this."
            submit="Remove the strike"
            pending={remove.isPending}
            onSubmit={(reason) => remove.mutate(reason)}
          />
        ) : (
          <div>
            <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setRemoving(true)}>
              Remove this strike
            </Button>
          </div>
        ))}
      {remove.isError && (
        <p role="alert" className="text-small text-danger">
          {errorMessage(remove.error)}
        </p>
      )}
    </li>
  );
}

export function StrikesSection({ sitterId }: { sitterId: string }) {
  const queryClient = useQueryClient();
  const key = ["admin", "strikes", sitterId];
  const strikes = useQuery({ queryKey: key, queryFn: () => apiFetch<AdminStrikes>(`/admin/sitters/${sitterId}/strikes`) });
  const [adding, setAdding] = useState(false);
  const add = useMutation({
    mutationFn: (reason: string) =>
      apiFetch<AdminStrikes>(`/admin/sitters/${sitterId}/strikes`, { method: "POST", body: JSON.stringify({ reason }) }),
    onSuccess: (updated) => {
      queryClient.setQueryData(key, updated);
      setAdding(false);
    },
  });

  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3">
      <h2 className="text-h3">Strikes</h2>
      {strikes.isPending && <p className="text-muted">Loading…</p>}
      {strikes.isError && (
        <p role="alert" className="text-danger">
          {errorMessage(strikes.error)}
        </p>
      )}
      {strikes.isSuccess && (
        <>
          <p className="text-ink">
            {strikes.data.counting === 0
              ? "No strikes in the last 6 months."
              : `${strikes.data.counting} in the last 6 months.`}{" "}
            {strikes.data.blocked_until
              ? `Blocked from new bookings until ${when(strikes.data.blocked_until)}.`
              : "Not blocked."}
          </p>
          {strikes.data.strikes.length > 0 && (
            <ul>
              {strikes.data.strikes.map((strike) => (
                <StrikeRow key={strike.id} strike={strike} sitterId={sitterId} />
              ))}
            </ul>
          )}
          {adding ? (
            <ReasonForm
              label="Why give a strike? The sitter sees this."
              submit="Give the strike"
              pending={add.isPending}
              onSubmit={(reason) => add.mutate(reason)}
            />
          ) : (
            <div>
              <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setAdding(true)}>
                Give a strike
              </Button>
            </div>
          )}
          {add.isError && (
            <p role="alert" className="text-small text-danger">
              {errorMessage(add.error)}
            </p>
          )}
        </>
      )}
    </Card>
  );
}
