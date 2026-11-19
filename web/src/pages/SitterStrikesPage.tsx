import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ChangeEvent } from "react";
import { Card, EmptyState } from "../components/ui";
import { clientCheck } from "../components/documents/DocumentUpload";
import { ApiError, apiFetch } from "../lib/api";
import { formatDate, formatDay, formatTime } from "../lib/format";

// The sitter's strikes (CLAUDE.md 6.5 and 6.6): what blocks her from new bookings and until when. A strike
// counts for 6 months. For a late cancellation because she was ill she can send a doctor's note; an admin
// looks at it and can remove the strike.

export type SitterStrike = {
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
};

export type SitterStrikes = { blocked_until: string | null; counting: number; strikes: SitterStrike[] };

export const STRIKES_KEY = ["sitter", "strikes"];

function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

function strikeTitle(strike: SitterStrike): string {
  if (strike.reason === "late_cancellation") {
    return strike.booking_starts_at
      ? `Late cancellation of the booking on ${when(strike.booking_starts_at)}`
      : "Late cancellation";
  }
  if (strike.reason === "no_show") return "Missed booking";
  return "Given by Pacifyco";
}

/** Upload the note, then link it to the strike. */
async function sendDoctorNote(strikeId: string, file: File): Promise<SitterStrikes> {
  const ticket = await apiFetch<{ document_id: string; upload_url: string }>("/documents/upload-url", {
    method: "POST",
    body: JSON.stringify({ type: "doctor_note", child_id: null }),
  });
  const put = await fetch(ticket.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
  if (!put.ok) throw new ApiError(put.status, "upload_failed", "That upload didn't go through. Please try again.");
  const confirmed = await apiFetch<{ status: string }>(`/documents/${ticket.document_id}/confirm`, { method: "POST" });
  if (confirmed.status !== "uploaded") {
    throw new ApiError(422, "invalid_file", "Please upload a PDF, JPG or PNG of at most 5 MB.");
  }
  return apiFetch<SitterStrikes>(`/sitter/strikes/${strikeId}/doctor-note`, {
    method: "POST",
    body: JSON.stringify({ document_id: ticket.document_id }),
  });
}

function DoctorNote({ strike }: { strike: SitterStrike }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const send = useMutation({
    mutationFn: (file: File) => sendDoctorNote(strike.id, file),
    onSuccess: (updated) => queryClient.setQueryData(STRIKES_KEY, updated),
    onError: (failed) => setError(failed instanceof ApiError ? failed.message : "That didn't go through. Please try again."),
  });
  if (strike.doctor_note_sent) {
    return <p className="text-small text-muted">Doctor's note sent. Pacifyco is looking at it.</p>;
  }
  function chosen(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const problem = clientCheck(file, "doctor_note");
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    send.mutate(file);
  }
  return (
    <div className="flex flex-col gap-1">
      <label className="text-small text-ink">
        Were you ill? Send your doctor's note (PDF, JPG or PNG) and Pacifyco will look at it. If it's accepted, the
        strike is removed.
        <input
          type="file"
          accept="application/pdf,image/jpeg,image/png"
          onChange={chosen}
          disabled={send.isPending}
          className="mt-2 block text-small"
        />
      </label>
      {send.isPending && <p className="text-small text-muted">Sending…</p>}
      {error && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export function SitterStrikesPage() {
  const strikes = useQuery({ queryKey: STRIKES_KEY, queryFn: () => apiFetch<SitterStrikes>("/sitter/strikes") });

  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-4">
      <h1>Your strikes</h1>
      {strikes.isPending && <p className="text-center text-muted">Loading…</p>}
      {strikes.isError && (
        <p role="alert" className="text-danger">
          We couldn't load your strikes. Please try again.
        </p>
      )}
      {strikes.isSuccess && (
        <>
          {strikes.data.blocked_until && (
            <Card as="section" padding="roomy" role="alert" className="border-l-4 border-coral">
              <p className="text-ink">
                You can't take new bookings until {when(strikes.data.blocked_until)}. Your confirmed bookings stay.
              </p>
            </Card>
          )}
          <p className="text-small text-muted">
            A strike counts for 6 months. Each one stops new bookings for a while: 24 hours for the first, then 3
            days, 1 week and 2 weeks. A fifth strike in 6 months removes your account.
          </p>
          {strikes.data.strikes.length === 0 ? (
            <EmptyState message="No strikes. Thank you for being reliable." />
          ) : (
            <Card as="section" padding="roomy">
              <ul>
                {strikes.data.strikes.map((strike) => {
                  const expired = new Date(strike.expires_at) <= new Date();
                  return (
                    <li key={strike.id} className="flex flex-col gap-2 border-t border-line py-4 first:border-t-0">
                      <p className="text-ui text-ink">{strikeTitle(strike)}</p>
                      {strike.note && <p className="text-small text-ink">{strike.note}</p>}
                      <p className="text-small text-muted">
                        {strike.removed_at
                          ? `Removed: ${strike.removal_reason ?? ""}`
                          : expired
                            ? `Given ${formatDate(new Date(strike.given_at))}. No longer counts.`
                            : `Given ${formatDate(new Date(strike.given_at))}. Counts until ${formatDate(new Date(strike.expires_at))}.`}
                      </p>
                      {strike.reason === "late_cancellation" && !strike.removed_at && !expired && (
                        <DoctorNote strike={strike} />
                      )}
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </>
      )}
    </section>
  );
}
