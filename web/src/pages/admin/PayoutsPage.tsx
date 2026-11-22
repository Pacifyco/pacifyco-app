import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { BackLink, Button, Card, EmptyState, TextInput, showToast } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDay, formatMobile, formatTime } from "../../lib/format";
import { earningLabel, type EarningKind } from "../../lib/earnings";
import { rupees } from "../../lib/prices";
import { errorMessage } from "./shared";

// Payouts due (CLAUDE.md 6.10): every released, unpaid earning, by sitter (one transfer for everything due
// to her; Reuben, 2026-11-22), soonest deadline first, each with a countdown to its 12-hour deadline.
// Bank details are shown, and the API logs each time; so the list isn't refetched on a timer, only the
// countdowns tick. "Mark paid" records the transfer reference for exactly the earnings shown.

export type DueEarning = {
  id: string;
  booking_id: string;
  booking_starts_at: string;
  kind: EarningKind;
  amount_paise: number;
  minutes: number | null;
  due_by: string;
};

export type SitterDue = {
  sitter_id: string;
  sitter_name: string | null;
  sitter_phone: string | null;
  payout_method: "bank" | "upi" | null;
  upi_id: string | null;
  bank: { account_holder_name: string; account_number: string; ifsc_code: string } | null;
  total_paise: number;
  next_due_by: string;
  earnings: DueEarning[];
};

export { earningLabel };

export type PayoutsSummary = { due: number; overdue: number };

export const PAYOUTS_SUMMARY_KEY = ["admin", "payouts", "summary"];
const PAYOUTS_KEY = ["admin", "payouts"];

function hoursAndMinutes(ms: number): string {
  const totalMinutes = Math.max(1, Math.ceil(ms / 60_000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes} min`;
  return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`;
}

/** "Due in 11 h 40 min", or "Overdue by 25 min". */
export function countdown(dueBy: string, now: Date): { text: string; overdue: boolean } {
  const left = new Date(dueBy).getTime() - now.getTime();
  return left > 0
    ? { text: `Due in ${hoursAndMinutes(left)}`, overdue: false }
    : { text: `Overdue by ${hoursAndMinutes(-left)}`, overdue: true };
}

function useNow(everyMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), everyMs);
    return () => clearInterval(timer);
  }, [everyMs]);
  return now;
}

function HowToPay({ group }: { group: SitterDue }) {
  if (group.payout_method === "upi" && group.upi_id) {
    return <p className="text-ink">UPI: {group.upi_id}</p>;
  }
  if (group.payout_method === "bank" && group.bank) {
    return (
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 text-ink">
        <dt className="text-muted">Account holder</dt>
        <dd>{group.bank.account_holder_name}</dd>
        <dt className="text-muted">Account number</dt>
        <dd>{group.bank.account_number}</dd>
        <dt className="text-muted">IFSC</dt>
        <dd>{group.bank.ifsc_code}</dd>
      </dl>
    );
  }
  return <p className="text-danger">No payout details. Call her before paying.</p>;
}

function MarkPaid({ group }: { group: SitterDue }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | undefined>();
  const markPaid = useMutation({
    mutationFn: () =>
      apiFetch(`/admin/payouts/${group.sitter_id}/paid`, {
        method: "POST",
        body: JSON.stringify({
          earning_ids: group.earnings.map((earning) => earning.id),
          transfer_reference: reference.trim(),
        }),
      }),
    onSuccess: async () => {
      showToast(`Marked paid: ${rupees(group.total_paise)} to ${group.sitter_name ?? "her"}`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: PAYOUTS_KEY, exact: true }),
        queryClient.invalidateQueries({ queryKey: PAYOUTS_SUMMARY_KEY }),
      ]);
    },
    onError: (failed) => setError(errorMessage(failed)),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!reference.trim()) return setError("Enter the UPI reference or bank transfer reference (UTR).");
    setError(undefined);
    markPaid.mutate();
  }

  if (!open) {
    return (
      <div>
        <Button variant="secondary" fullWidthOnPhone={false} onClick={() => setOpen(true)}>
          Mark paid
        </Button>
      </div>
    );
  }
  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3">
      <TextInput
        label="Transfer reference"
        hint={`After sending ${rupees(group.total_paise)}: the UPI reference, or the bank transfer's UTR.`}
        maxLength={40}
        value={reference}
        error={error}
        onChange={(event) => setReference(event.target.value)}
      />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="secondary" loading={markPaid.isPending}>
          Mark {rupees(group.total_paise)} paid
        </Button>
        <Button variant="tertiary" onClick={() => setOpen(false)}>
          Back
        </Button>
      </div>
    </form>
  );
}

function SitterDueCard({ group, now }: { group: SitterDue; now: Date }) {
  const next = countdown(group.next_due_by, now);
  return (
    <li
      className={`flex flex-col gap-3 border-t border-line py-5 first:border-t-0 ${next.overdue ? "border-l-4 border-l-coral pl-3" : ""}`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-ui text-ink">{group.sitter_name ?? "Name not given"}</p>
        <p className={`text-ui ${next.overdue ? "text-danger" : "text-ink"}`}>{rupees(group.total_paise)}</p>
      </div>
      <p className={next.overdue ? "text-danger" : "text-muted"}>{next.text}</p>
      {group.sitter_phone && (
        <a href={`tel:${group.sitter_phone}`} className="text-ui">
          {formatMobile(group.sitter_phone)}
        </a>
      )}
      <HowToPay group={group} />
      <ul className="flex flex-col gap-2" aria-label={`Due to ${group.sitter_name ?? "her"}`}>
        {group.earnings.map((earning) => {
          const due = countdown(earning.due_by, now);
          const starts = new Date(earning.booking_starts_at);
          return (
            <li key={earning.id} className="flex flex-wrap justify-between gap-2 text-small">
              <span className="text-ink">
                {earningLabel(earning)} · booking {formatDay(starts)}, {formatTime(starts)}
              </span>
              <span className={due.overdue ? "text-danger" : "text-muted"}>
                {rupees(earning.amount_paise)} · {due.text}
              </span>
            </li>
          );
        })}
      </ul>
      {group.payout_method && <MarkPaid group={group} />}
    </li>
  );
}

export function PayoutsPage() {
  const now = useNow();
  const due = useQuery({ queryKey: PAYOUTS_KEY, queryFn: () => apiFetch<SitterDue[]>("/admin/payouts") });
  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-4">
      <BackLink to="/admin" label="Admin" />
      <h1>Payouts due</h1>
      {due.isPending && <p className="text-muted">Loading…</p>}
      {due.isError && (
        <p role="alert" className="text-danger">
          {errorMessage(due.error)}
        </p>
      )}
      {due.isSuccess &&
        (due.data.length === 0 ? (
          <EmptyState message="Nothing to pay right now." />
        ) : (
          <Card as="section" padding="roomy" aria-label="Payouts due">
            <ul>
              {due.data.map((group) => (
                <SitterDueCard key={group.sitter_id} group={group} now={now} />
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}
