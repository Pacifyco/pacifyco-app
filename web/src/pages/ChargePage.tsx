import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router";
import { BackLink, ButtonLink, Card, EmptyState } from "../components/ui";
import { apiFetch } from "../lib/api";
import { formatDay, formatTime } from "../lib/format";
import { rupees } from "../lib/prices";
import { ReferenceForm, UpiDetails, type PayByUpi } from "./BookSitterPage";
import { firstNameOf } from "./FindSittersPage";

// Paying a charge (CLAUDE.md 6.5; overtime uses this page in phase 8): money owed blocks new bookings
// (6.4). Pay by UPI and send the 12-digit reference; once Pacifyco has checked it, it's paid.

export type Charge = {
  id: string;
  kind: "cancellation_charge" | "overtime";
  amount_paise: number;
  status: "pending" | "confirmed" | "waived";
  upi_reference: string | null;
  rejection_reason: string | null;
  waive_reason: string | null;
  booking_id: string;
  booking_starts_at: string;
  sitter_name: string | null;
  pay_by_upi: PayByUpi | null;
};

const TITLES: Record<Charge["kind"], string> = {
  cancellation_charge: "Late cancellation charge",
  overtime: "Overtime",
};

function chargeKey(chargeId: string) {
  return ["parent", "charge", chargeId];
}

export function ChargePage() {
  const { paymentId = "" } = useParams();
  const charge = useQuery({
    queryKey: chargeKey(paymentId),
    queryFn: () => apiFetch<Charge>(`/parent/payments/${paymentId}`),
  });
  if (charge.isPending) return <p className="text-center text-muted">Loading…</p>;
  if (charge.isError) {
    return (
      <section className="mx-auto max-w-[40rem]">
        <EmptyState
          message="We couldn't find that payment."
          action={<ButtonLink to="/parent/payments">Your payments</ButtonLink>}
        />
      </section>
    );
  }
  const data = charge.data;
  const starts = new Date(data.booking_starts_at);
  const sitter = data.sitter_name ? firstNameOf(data.sitter_name) : "your sitter";
  return (
    <article className="mx-auto flex max-w-[40rem] flex-col gap-6">
      <BackLink to="/parent/payments" label="Your payments" />
      <h1>{TITLES[data.kind]}</h1>
      <Card as="section" padding="roomy" className="flex flex-col gap-2">
        <p className="text-h3 text-ink">{rupees(data.amount_paise)}</p>
        <p className="text-small text-muted">
          For the booking with {sitter} on {formatDay(starts)}, {formatTime(starts)}
        </p>
      </Card>

      {data.status === "confirmed" ? (
        <Card as="section" padding="roomy">
          <p className="text-ink">Paid. Thank you.</p>
        </Card>
      ) : data.status === "waived" ? (
        <Card as="section" padding="roomy" className="flex flex-col gap-2">
          <p className="text-ink">Pacifyco has waived this charge, so you don't need to pay it.</p>
          {data.waive_reason && <p className="text-small text-muted">{data.waive_reason}</p>}
        </Card>
      ) : data.upi_reference ? (
        <Card as="section" padding="roomy" className="flex flex-col gap-2">
          <h2 className="text-h3">Payment sent</h2>
          <p className="text-ink">
            UPI reference {data.upi_reference}. Pacifyco is checking it. You can book again once it's confirmed.
          </p>
        </Card>
      ) : (
        <Card as="section" padding="roomy" className="flex flex-col gap-4">
          <h2 className="text-h3">Pay {rupees(data.amount_paise)} by UPI</h2>
          {data.rejection_reason && (
            <p role="alert" className="text-danger">
              We couldn't confirm your payment: {data.rejection_reason} Please check the UPI reference and send it
              again.
            </p>
          )}
          <p className="text-ink">You can't make new bookings until this is paid.</p>
          {data.pay_by_upi ? (
            <>
              <UpiDetails upi={data.pay_by_upi} />
              <ReferenceForm path={`/parent/payments/${data.id}/payment`} queryKey={chargeKey(data.id)} />
            </>
          ) : (
            <p className="text-ink">We can't take payments just yet. Please check back soon.</p>
          )}
        </Card>
      )}
    </article>
  );
}
