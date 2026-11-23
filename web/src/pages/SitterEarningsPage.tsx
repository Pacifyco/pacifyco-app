import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { Card, EmptyState } from "../components/ui";
import { apiFetch } from "../lib/api";
import { earningLabel, type EarningKind } from "../lib/earnings";
import { formatDate, formatDay, formatTime } from "../lib/format";
import { rupees } from "../lib/prices";

// The sitter's earnings (CLAUDE.md 6.10): what's due to her (Pacifyco pays it within 12 hours), what's on
// hold, what she's been paid, and each payout. Never the price the family paid.

export type SitterEarning = {
  id: string;
  booking_id: string;
  booking_starts_at: string;
  family_name: string;
  kind: EarningKind;
  amount_paise: number;
  minutes: number | null;
  note: string | null; // extra pay's reason, from Pacifyco
  status: "held" | "released" | "paid";
  due_by: string | null;
  paid_at: string | null;
};

export type SitterPayout = {
  id: string;
  amount_paise: number;
  method: "bank" | "upi";
  transfer_reference: string;
  paid_at: string;
};

export type SitterEarnings = {
  held_paise: number;
  due_paise: number;
  paid_paise: number;
  earnings: SitterEarning[];
  payouts: SitterPayout[];
};

function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

/** Where an earning is, in her words. */
export function earningStatusText(earning: SitterEarning): string {
  if (earning.status === "paid") return earning.paid_at ? `Paid ${formatDate(new Date(earning.paid_at))}` : "Paid";
  if (earning.status === "released" && earning.due_by) return `We'll pay this by ${when(earning.due_by)}`;
  return "On hold";
}

function Total({ label, paise, hint }: { label: string; paise: number; hint: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-small text-muted">{label}</span>
      <span className="text-h3 text-ink">{rupees(paise)}</span>
      <span className="text-small text-muted">{hint}</span>
    </div>
  );
}

export function SitterEarningsPage() {
  const earnings = useQuery({
    queryKey: ["sitter", "earnings"],
    queryFn: () => apiFetch<SitterEarnings>("/sitter/earnings"),
  });
  if (earnings.isPending) return <p className="text-muted">Loading…</p>;
  if (earnings.isError) {
    return (
      <p role="alert" className="text-danger">
        We couldn't load your earnings. Please try again.
      </p>
    );
  }
  const data = earnings.data;
  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-4">
      <h1>Earnings</h1>
      <Card as="section" padding="roomy" aria-label="Your totals" className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Total label="Due to you" paise={data.due_paise} hint="We pay within 12 hours." />
        <Total label="On hold" paise={data.held_paise} hint="Until the booking is finished." />
        <Total label="Paid so far" paise={data.paid_paise} hint="All time." />
      </Card>
      {data.held_paise > 0 && (
        <p className="text-small text-muted">
          Pay is on hold until the booking has ended, you've answered any overtime request, and anything reported
          during it has been sorted out.
        </p>
      )}

      <h2 className="text-ui font-semibold">Your earnings</h2>
      {data.earnings.length === 0 ? (
        <EmptyState message="Nothing yet. Your pay shows here once a booking ends." />
      ) : (
        <Card as="section" padding="roomy" aria-label="Your earnings">
          <ul>
            {data.earnings.map((earning) => (
              <li key={earning.id} className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-ink">{earningLabel(earning)}</span>
                  <span className="text-ui text-ink">{rupees(earning.amount_paise)}</span>
                </div>
                <Link to={`/sitter/bookings/${earning.booking_id}`} className="text-small">
                  {earning.family_name}'s booking, {when(earning.booking_starts_at)}
                </Link>
                <span className={`text-small ${earning.status === "held" ? "text-muted" : "text-ink"}`}>
                  {earningStatusText(earning)}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {data.payouts.length > 0 && (
        <>
          <h2 className="text-ui font-semibold">Payments to you</h2>
          <Card as="section" padding="roomy" aria-label="Payments to you">
            <ul>
              {data.payouts.map((payout) => (
                <li key={payout.id} className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="text-ink">{when(payout.paid_at)}</span>
                    <span className="text-ui text-ink">{rupees(payout.amount_paise)}</span>
                  </div>
                  <span className="text-small text-muted">
                    {payout.method === "upi" ? "By UPI" : "To your bank account"} · reference{" "}
                    {payout.transfer_reference}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </section>
  );
}
