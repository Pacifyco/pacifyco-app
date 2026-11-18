import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import { BackLink, Card, EmptyState, ButtonLink } from "../components/ui";
import { apiFetch } from "../lib/api";
import { formatDay, formatTime } from "../lib/format";
import { rupees } from "../lib/prices";
import { firstNameOf } from "./FindSittersPage";

// "Your payments" (CLAUDE.md 6.1; phase 6): every payment, charge and refund, newest first, each linked
// to its booking. Unpaid charges are money owed, and block new bookings (6.4). Never a plan's name.

type Kind = "booking" | "overtime" | "refund" | "cancellation_charge";
type Status = "pending" | "confirmed" | "rejected";

export type PaymentHistoryItem = {
  id: string;
  kind: Kind;
  amount_paise: number; // always positive; the kind says which way the money went
  status: Status;
  upi_reference: string | null;
  transfer_reference: string | null;
  rejection_reason: string | null;
  created_at: string;
  decided_at: string | null;
  booking_id: string;
  booking_starts_at: string;
  sitter_name: string | null;
};

export type PaymentHistory = { owed_paise: number; payments: PaymentHistoryItem[] };

const TITLES: Record<Kind, string> = {
  booking: "Booking payment",
  overtime: "Overtime",
  refund: "Refund",
  cancellation_charge: "Late cancellation charge",
};

/** Where the money is, in the parent's words. */
export function statusText(item: PaymentHistoryItem): string {
  if (item.kind === "refund") {
    return item.status === "confirmed"
      ? `Refunded${item.transfer_reference ? ` (reference ${item.transfer_reference})` : ""}`
      : "Pacifyco is refunding you";
  }
  if (item.kind === "booking") {
    if (item.status === "pending") return "Pacifyco is checking it";
    if (item.status === "rejected") return `Not confirmed: ${item.rejection_reason ?? "please check the reference"}`;
    return "Paid";
  }
  return item.status === "confirmed" ? "Paid" : item.status === "rejected" ? "Not confirmed" : "To pay";
}

function PaymentRow({ item }: { item: PaymentHistoryItem }) {
  const starts = new Date(item.booking_starts_at);
  const sitter = item.sitter_name ? firstNameOf(item.sitter_name) : "your sitter";
  const refund = item.kind === "refund";
  return (
    <li className="border-t border-line first:border-t-0">
      <Link to={`/parent/bookings/${item.booking_id}`} className="flex items-center gap-4 py-4 text-ink no-underline">
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-ui">{TITLES[item.kind]}</span>
          <span className="text-small text-muted">
            {`With ${sitter} · ${formatDay(starts)}, ${formatTime(starts)}`}
          </span>
          <span className={item.status === "rejected" ? "text-small text-danger" : "text-small text-muted"}>
            {statusText(item)}
          </span>
        </span>
        <span className="text-ui font-semibold">
          {refund ? "+" : ""}
          {rupees(item.amount_paise)}
        </span>
        <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
      </Link>
    </li>
  );
}

export function ParentPaymentsPage() {
  const history = useQuery({ queryKey: ["parent", "payments"], queryFn: () => apiFetch<PaymentHistory>("/parent/payments") });

  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-4">
      <BackLink to="/parent/profile" label="Your profile" />
      <h1>Your payments</h1>
      {history.isPending && <p className="text-center text-muted">Loading…</p>}
      {history.isError && (
        <p role="alert" className="text-danger">
          We couldn't load your payments. Please try again.
        </p>
      )}
      {history.isSuccess && (
        <>
          {history.data.owed_paise > 0 && (
            <Card as="section" padding="roomy" role="alert">
              <p className="text-ink">
                You owe Pacifyco {rupees(history.data.owed_paise)}. You can't make new bookings until it's paid.
              </p>
            </Card>
          )}
          {history.data.payments.length === 0 ? (
            <EmptyState
              message="No payments yet. Payments for your bookings will show here."
              action={<ButtonLink to="/parent/sitters">Find a sitter</ButtonLink>}
            />
          ) : (
            <Card as="section" padding="roomy">
              <ul>
                {history.data.payments.map((item) => (
                  <PaymentRow key={item.id} item={item} />
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
    </section>
  );
}
