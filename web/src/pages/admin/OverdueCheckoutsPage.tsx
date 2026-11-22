import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { BackLink, Button, Card, EmptyState, Select, Textarea, showToast } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDay, formatMobile, formatTime } from "../../lib/format";
import { errorMessage } from "./shared";

// Overdue check-outs and locked codes (CLAUDE.md 6.7): a booking still checked in 30+ minutes past its
// end, or one whose codes got locked, needs an admin to call both people and, if it stays stuck, close
// it by hand with a reason. No overtime is charged by itself; the admin may choose whole hours to charge,
// and the parent is then asked to pay (Reuben, 2026-11-21).

export type NeedsAttentionItem = {
  booking_id: string;
  overdue: boolean; // otherwise its codes are locked
  starts_at: string;
  ends_at: string;
  parent_name: string | null;
  parent_phone: string | null;
  sitter_name: string | null;
  sitter_phone: string | null;
  checked_in: boolean; // if she never did, the admin may choose hours to pay her when closing it
};

export const NEEDS_ATTENTION_KEY = ["admin", "overdue-checkouts"];

function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

function Phone({ label, name, phone }: { label: string; name: string | null; phone: string | null }) {
  return (
    <div className="flex flex-col">
      <span className="text-small text-muted">{label}</span>
      <span className="text-ink">{name ?? "Not given"}</span>
      {phone && (
        <a href={`tel:${phone}`} className="text-ui">
          {formatMobile(phone)}
        </a>
      )}
    </div>
  );
}

function NeedsAttentionCard({ item }: { item: NeedsAttentionItem }) {
  const queryClient = useQueryClient();
  const [closing, setClosing] = useState(false);
  const [reason, setReason] = useState("");
  const [overtimeHours, setOvertimeHours] = useState("0");
  const [payHours, setPayHours] = useState("0"); // only if she never checked in (Reuben, 2026-11-22)
  const bookedHours = Math.round((new Date(item.ends_at).getTime() - new Date(item.starts_at).getTime()) / 3_600_000);
  const [error, setError] = useState<string | undefined>();
  const close = useMutation({
    mutationFn: () =>
      apiFetch<NeedsAttentionItem>(`/admin/bookings/${item.booking_id}/close`, {
        method: "POST",
        body: JSON.stringify({
          reason: reason.trim(),
          overtime_hours: overtimeHours === "0" ? null : Number(overtimeHours),
          pay_hours: item.checked_in || payHours === "0" ? null : Number(payHours),
        }),
      }),
    onSuccess: async () => {
      showToast(overtimeHours === "0" ? "Booking closed" : "Booking closed. The parent has been asked to pay the overtime.");
      await queryClient.invalidateQueries({ queryKey: NEEDS_ATTENTION_KEY });
    },
    onError: (failed) => setError(errorMessage(failed)),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return setError("Please say why you're closing it.");
    setError(undefined);
    close.mutate();
  }

  return (
    <li className="flex flex-col gap-4 border-t border-line py-5 first:border-t-0">
      <div className="flex flex-col gap-1">
        <p className="text-eyebrow text-muted uppercase">{item.overdue ? "Check-out overdue" : "Codes locked"}</p>
        <p className="text-ui text-ink">
          Booking {when(item.starts_at)} – {formatTime(new Date(item.ends_at))}
        </p>
        <p className="text-ink">
          {item.overdue
            ? "Still checked in more than 30 minutes past the end."
            : "Too many wrong codes were entered; code entry is locked."}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Phone label="Parent" name={item.parent_name} phone={item.parent_phone} />
        <Phone label="Sitter" name={item.sitter_name} phone={item.sitter_phone} />
      </div>
      {closing ? (
        <form noValidate onSubmit={submit} className="flex flex-col gap-3">
          <Textarea
            label="Why are you closing it?"
            hint="Recorded with the booking."
            rows={2}
            maxLength={500}
            value={reason}
            error={error}
            onChange={(event) => setReason(event.target.value)}
          />
          <Select
            label="Charge overtime?"
            hint="Not charged unless you choose. Priced as at check-out; the parent is emailed to pay within 2 hours."
            value={overtimeHours}
            onChange={(event) => setOvertimeHours(event.target.value)}
          >
            <option value="0">No overtime</option>
            {[1, 2, 3, 4, 5, 6].map((hours) => (
              <option key={hours} value={String(hours)}>
                {hours === 1 ? "1 hour" : `${hours} hours`}
              </option>
            ))}
          </Select>
          {!item.checked_in && (
            <Select
              label="Pay the sitter?"
              hint="She never checked in, so she isn't paid unless you choose hours here."
              value={payHours}
              onChange={(event) => setPayHours(event.target.value)}
            >
              <option value="0">Nothing</option>
              {Array.from({ length: bookedHours }, (_, index) => index + 1).map((hours) => (
                <option key={hours} value={String(hours)}>
                  {hours === 1 ? "1 hour" : `${hours} hours`}
                </option>
              ))}
            </Select>
          )}
          <div className="flex flex-wrap gap-3">
            <Button type="submit" variant="secondary" loading={close.isPending}>
              Close the booking
            </Button>
            <Button variant="tertiary" onClick={() => setClosing(false)}>
              Back
            </Button>
          </div>
        </form>
      ) : (
        <div>
          <Button variant="secondary" fullWidthOnPhone={false} onClick={() => setClosing(true)}>
            Close the booking
          </Button>
        </div>
      )}
      {error && !closing && (
        <p role="alert" className="text-small text-danger">
          {error}
        </p>
      )}
    </li>
  );
}

export function OverdueCheckoutsPage() {
  const needsAttention = useQuery({
    queryKey: NEEDS_ATTENTION_KEY,
    queryFn: () => apiFetch<NeedsAttentionItem[]>("/admin/overdue-checkouts"),
    refetchInterval: 30_000,
  });
  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-4">
      <BackLink to="/admin" label="Admin" />
      <h1>Overdue check-outs</h1>
      {needsAttention.isPending && <p className="text-muted">Loading…</p>}
      {needsAttention.isError && (
        <p role="alert" className="text-danger">
          {errorMessage(needsAttention.error)}
        </p>
      )}
      {needsAttention.isSuccess &&
        (needsAttention.data.length === 0 ? (
          <EmptyState message="Nothing needs attention." />
        ) : (
          <Card as="section" padding="roomy" aria-label="Bookings needing attention">
            <ul>
              {needsAttention.data.map((item) => (
                <NeedsAttentionCard key={item.booking_id} item={item} />
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}
