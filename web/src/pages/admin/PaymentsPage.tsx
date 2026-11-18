import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Button, Card, TextInput, Textarea, showToast } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDay, formatTime, plural } from "../../lib/format";
import { rupees } from "../../lib/prices";
import { errorMessage } from "./shared";

// Booking payments and refunds (CLAUDE.md 6.1; phase 6). Admins find each UPI reference in Pacifyco's
// account, then confirm or reject it (a rejection reason is shown to the parent). Confirming wins the
// sitter's time; if another booking took it first, a refund is owed, paid back by UPI or bank transfer
// and recorded here with its reference. Admins see the plan; parents never do.

type PaymentToCheck = {
  id: string;
  booking_id: string;
  parent_id: string;
  parent_name: string | null;
  parent_email: string;
  sitter_name: string | null;
  plan: string;
  starts_at: string;
  hours: number;
  amount_paise: number;
  upi_reference: string | null;
  note: string;
  sent_at: string;
  pay_by: string;
  booking_status: string;
  children_verified: boolean;
};

type RefundToPay = {
  id: string;
  booking_id: string;
  parent_id: string;
  parent_name: string | null;
  parent_email: string;
  amount_paise: number;
  paid_with_reference: string | null;
  owed_since: string;
  booking_status: string;
};

export type PaymentsQueue = { to_check: PaymentToCheck[]; refunds: RefundToPay[] };

type Decision = {
  status: string;
  booking_status: string;
  refund_owed: boolean;
  cancelled_bookings: number;
};

export const PAYMENTS_KEY = ["admin", "payments"];

const PLAN_NAMES: Record<string, string> = { pause: "Pause", unwind: "Unwind", recharge: "Recharge" };

function when(iso: string): string {
  const date = new Date(iso);
  return `${formatDay(date)}, ${formatTime(date)}`;
}

/** What happened, in one line, for the toast after confirming. */
export function confirmedMessage(decision: Decision): string {
  if (decision.refund_owed) return "Payment recorded. The time was already taken, so a refund is owed.";
  const booking =
    decision.booking_status === "confirmed"
      ? "The booking is confirmed."
      : "The booking is paid and waits for a child's verification.";
  const others = decision.cancelled_bookings
    ? ` ${plural(decision.cancelled_bookings, "other booking", "other bookings")} for that time cancelled.`
    : "";
  return `Payment confirmed. ${booking}${others}`;
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <dt className="text-small text-muted">{label}</dt>
      <dd className="text-ink">{children}</dd>
    </div>
  );
}

function PaymentItem({ payment }: { payment: PaymentToCheck }) {
  const queryClient = useQueryClient();
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string>();

  const decide = useMutation({
    mutationFn: (rejectWith: string | null) =>
      apiFetch<Decision>(`/admin/payments/${payment.id}/${rejectWith === null ? "confirm" : "reject"}`, {
        method: "POST",
        ...(rejectWith === null ? {} : { body: JSON.stringify({ reason: rejectWith }) }),
      }),
    onSuccess: async (decision, rejectWith) => {
      showToast(rejectWith === null ? confirmedMessage(decision) : "Payment rejected. The parent has been told why.");
      await queryClient.invalidateQueries({ queryKey: PAYMENTS_KEY });
    },
    onError: (failed) => setError(errorMessage(failed)),
  });

  function reject(event: FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return setError("Please give a reason. It's shown to the parent.");
    setError(undefined);
    decide.mutate(reason.trim());
  }

  return (
    <li className="flex flex-col gap-4 border-t border-line py-5 first:border-t-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-h3 text-ink">{rupees(payment.amount_paise)}</p>
        <p className="text-ui text-ink">
          UPI reference <span className="font-semibold select-all">{payment.upi_reference ?? "none"}</span>
        </p>
      </div>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Detail label="Parent">
          {payment.parent_name ?? payment.parent_email}
          <span className="block text-small text-muted">{payment.parent_email}</span>
        </Detail>
        <Detail label="Sitter and plan">
          {payment.sitter_name ?? "Sitter"} · {PLAN_NAMES[payment.plan] ?? payment.plan}
        </Detail>
        <Detail label="Booking">
          {when(payment.starts_at)} · {plural(payment.hours, "hour", "hours")}
        </Detail>
        <Detail label="Note on the payment">{payment.note}</Detail>
        <Detail label="Sent">{when(payment.sent_at)}</Detail>
        <Detail label="Pay by">{when(payment.pay_by)}</Detail>
        <Detail label="Children">
          {payment.children_verified ? "All verified" : "Not all verified yet: it will wait for them"}
        </Detail>
      </dl>
      {rejecting ? (
        <form noValidate onSubmit={reject} className="flex flex-col gap-3">
          <Textarea
            label="Why are you rejecting it?"
            hint="The parent sees this."
            rows={2}
            maxLength={500}
            value={reason}
            error={error}
            onChange={(event) => setReason(event.target.value)}
          />
          <div className="flex flex-wrap gap-3">
            <Button type="submit" variant="secondary" loading={decide.isPending}>
              Reject payment
            </Button>
            <Button variant="tertiary" onClick={() => setRejecting(false)}>
              Back
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-3">
            <Button loading={decide.isPending} onClick={() => decide.mutate(null)}>
              Confirm received
            </Button>
            <Button variant="secondary" onClick={() => setRejecting(true)}>
              Reject
            </Button>
          </div>
          {error && (
            <p role="alert" className="text-small text-danger">
              {error}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

function RefundItem({ refund }: { refund: RefundToPay }) {
  const queryClient = useQueryClient();
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string>();
  const paid = useMutation({
    mutationFn: (transfer_reference: string) =>
      apiFetch(`/admin/refunds/${refund.id}/paid`, {
        method: "POST",
        body: JSON.stringify({ transfer_reference }),
      }),
    onSuccess: async () => {
      showToast("Refund recorded. The parent has been told.");
      await queryClient.invalidateQueries({ queryKey: PAYMENTS_KEY });
    },
    onError: (failed) => setError(errorMessage(failed)),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!reference.trim()) return setError("Please enter the UPI or bank transfer reference.");
    setError(undefined);
    paid.mutate(reference.trim());
  }

  return (
    <li className="flex flex-col gap-4 border-t border-line py-5 first:border-t-0">
      <p className="text-h3 text-ink">Pay back {rupees(refund.amount_paise)}</p>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Detail label="Parent">
          {refund.parent_name ?? refund.parent_email}
          <span className="block text-small text-muted">{refund.parent_email}</span>
        </Detail>
        <Detail label="They paid with UPI reference">{refund.paid_with_reference ?? "Not recorded"}</Detail>
        <Detail label="Owed since">{when(refund.owed_since)}</Detail>
      </dl>
      <form noValidate onSubmit={submit} className="flex flex-col gap-3">
        <TextInput
          label="Refund reference"
          hint="The UPI or bank transfer reference of the refund you've sent."
          maxLength={100}
          autoComplete="off"
          value={reference}
          error={error}
          onChange={(event) => setReference(event.target.value)}
        />
        <div>
          <Button type="submit" loading={paid.isPending}>
            Mark refunded
          </Button>
        </div>
      </form>
    </li>
  );
}

export function PaymentsPage() {
  const queue = useQuery({ queryKey: PAYMENTS_KEY, queryFn: () => apiFetch<PaymentsQueue>("/admin/payments") });

  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <div className="text-center">
        <h1>Payments</h1>
        <p className="mt-4 text-muted">
          Find each UPI reference in Pacifyco's account, then confirm or reject it. Pay refunds back and record them.
        </p>
      </div>
      {queue.isPending && <p className="text-center text-muted">Loading…</p>}
      {queue.isError && (
        <p role="alert" className="text-center text-danger">
          {errorMessage(queue.error)}
        </p>
      )}
      {queue.isSuccess && (
        <>
          <Card as="section" padding="roomy" aria-labelledby="to-check-heading">
            <h2 id="to-check-heading" className="text-h3">
              Payments to check
            </h2>
            {queue.data.to_check.length === 0 ? (
              <p className="mt-3 text-muted">No payments are waiting.</p>
            ) : (
              <ul className="mt-3">
                {queue.data.to_check.map((payment) => (
                  <PaymentItem key={payment.id} payment={payment} />
                ))}
              </ul>
            )}
          </Card>
          <Card as="section" padding="roomy" aria-labelledby="refunds-heading">
            <h2 id="refunds-heading" className="text-h3">
              Refunds to pay
            </h2>
            {queue.data.refunds.length === 0 ? (
              <p className="mt-3 text-muted">No refunds are owed.</p>
            ) : (
              <ul className="mt-3">
                {queue.data.refunds.map((refund) => (
                  <RefundItem key={refund.id} refund={refund} />
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </section>
  );
}
