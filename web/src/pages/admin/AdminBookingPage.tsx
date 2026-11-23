import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { BackLink, Button, Card, Textarea, TextInput } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { earningLabel, type EarningKind } from "../../lib/earnings";
import { formatDay, formatTime } from "../../lib/format";
import { rupees } from "../../lib/prices";
import { adminStatusText } from "./BookingsPage";
import { errorMessage } from "./shared";

// One booking, for admins (phase 10; Reuben, 2026-11-23): the people, the money, her earnings and what
// happened. Adjustments, each with a reason, audit logged and emailed to the people affected: cancel it
// (before the start, refunded, no strike), refund part of it, add pay for the sitter, waive a charge.

type Person = { id: string; full_name: string | null; email: string; phone: string | null };

type Money = {
  id: string;
  kind: "booking" | "overtime" | "refund" | "cancellation_charge";
  amount_paise: number;
  status: "pending" | "confirmed" | "rejected" | "waived";
  upi_reference: string | null;
  transfer_reference: string | null;
  rejection_reason: string | null;
  waive_reason: string | null;
  created_at: string;
  decided_at: string | null;
  can_waive: boolean;
};

type Earning = {
  id: string;
  kind: EarningKind;
  amount_paise: number;
  minutes: number | null;
  note: string | null;
  status: "held" | "released" | "paid";
  due_by: string | null;
};

type BookingEvent = { action: string; by: string | null; at: string; after: Record<string, unknown> | null };

export type AdminBooking = {
  id: string;
  status: string;
  plan: "pause" | "unwind" | "recharge";
  units: number;
  children: string[];
  starts_at: string;
  ends_at: string;
  price_paise: number;
  created_at: string;
  parent: Person;
  sitter: Person;
  checked_in_at: string | null;
  checked_out_at: string | null;
  codes_locked: boolean;
  close_reason: string | null;
  payments: Money[];
  earnings: Earning[];
  refundable_paise: number;
  can_cancel: boolean;
  can_add_pay: boolean;
  history: BookingEvent[];
};

const MONEY_WORDS: Record<Money["kind"], string> = {
  booking: "Booking payment",
  overtime: "Overtime charge",
  refund: "Refund",
  cancellation_charge: "Late cancellation charge",
};

const MONEY_STATUS: Record<Money["status"], string> = {
  pending: "Waiting",
  confirmed: "Done",
  rejected: "Rejected",
  waived: "Waived",
};

const EARNING_STATUS: Record<Earning["status"], string> = { held: "On hold", released: "Due", paid: "Paid" };

function when(iso: string): string {
  const moment = new Date(iso);
  return `${formatDay(moment)}, ${formatTime(moment)}`;
}

/** "₹1,398" from "1398" or "1,398.50"; null if it isn't an amount. */
export function paiseFrom(text: string): number | null {
  const cleaned = text.replace(/[₹,\s]/g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  const paise = Math.round(Number(cleaned) * 100);
  return paise > 0 ? paise : null;
}

function bookingKey(id: string) {
  return ["admin", "booking", id];
}

function useAdjust(bookingId: string, path: string, onDone: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<AdminBooking>(`/admin/${path}`, { method: "POST", body: JSON.stringify(body) }),
    onSuccess: (updated) => {
      queryClient.setQueryData(bookingKey(bookingId), updated);
      void queryClient.invalidateQueries({ queryKey: ["admin", "bookings"] });
      onDone();
    },
  });
}

/** A reason, and an amount if `amountLabel` is given; sent with `submit`. */
function AdjustForm({
  bookingId,
  path,
  reasonLabel,
  amountLabel,
  amountHint,
  submit,
  onDone,
}: {
  bookingId: string;
  path: string;
  reasonLabel: string;
  amountLabel?: string;
  amountHint?: string;
  submit: string;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState("");
  const [errors, setErrors] = useState<{ reason?: string; amount?: string }>({});
  const send = useAdjust(bookingId, path, onDone);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const found: typeof errors = {};
    const paise = amountLabel ? paiseFrom(amount) : null;
    if (amountLabel && paise === null) found.amount = "Enter an amount in rupees, like 500.";
    if (!reason.trim()) found.reason = "Please give a reason.";
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    send.mutate(amountLabel ? { amount_paise: paise, reason: reason.trim() } : { reason: reason.trim() });
  }

  return (
    <form noValidate onSubmit={onSubmit} className="flex flex-col gap-3 border-t border-line pt-4">
      {amountLabel && (
        <TextInput
          label={amountLabel}
          hint={amountHint}
          inputMode="decimal"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          error={errors.amount}
        />
      )}
      <Textarea
        label={reasonLabel}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        error={errors.reason}
      />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" variant="secondary" fullWidthOnPhone={false} loading={send.isPending}>
          {submit}
        </Button>
        <Button type="button" variant="tertiary" fullWidthOnPhone={false} onClick={onDone}>
          Cancel
        </Button>
      </div>
      {send.isError && (
        <p role="alert" className="text-small text-danger">
          {errorMessage(send.error)}
        </p>
      )}
    </form>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = `${title.toLowerCase().replaceAll(" ", "-")}-heading`;
  return (
    <Card as="section" padding="roomy" className="flex flex-col gap-3" aria-labelledby={id}>
      <h2 id={id} className="text-h3">
        {title}
      </h2>
      {children}
    </Card>
  );
}

function MoneyRow({ item, bookingId }: { item: Money; bookingId: string }) {
  const [waiving, setWaiving] = useState(false);
  return (
    <li className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0">
      <p className="text-ui text-ink">
        {MONEY_WORDS[item.kind]} · {rupees(Math.abs(item.amount_paise))} · {MONEY_STATUS[item.status]}
      </p>
      <p className="text-small text-muted">
        {when(item.created_at)}
        {item.upi_reference ? ` · UPI ${item.upi_reference}` : ""}
        {item.transfer_reference ? ` · paid back, reference ${item.transfer_reference}` : ""}
      </p>
      {item.rejection_reason && <p className="text-small text-ink">Rejected: {item.rejection_reason}</p>}
      {item.waive_reason && <p className="text-small text-ink">Waived: {item.waive_reason}</p>}
      {item.can_waive &&
        (waiving ? (
          <AdjustForm
            bookingId={bookingId}
            path={`charges/${item.id}/waive`}
            reasonLabel="Why waive it? The parent sees this."
            submit="Waive the charge"
            onDone={() => setWaiving(false)}
          />
        ) : (
          <div>
            <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setWaiving(true)}>
              Waive this charge
            </Button>
          </div>
        ))}
    </li>
  );
}

type Choice = "cancel" | "refund" | "pay";

function Adjustments({ booking }: { booking: AdminBooking }) {
  const [choice, setChoice] = useState<Choice | null>(null);
  const done = () => setChoice(null);
  const nothing = !booking.can_cancel && booking.refundable_paise === 0 && !booking.can_add_pay;
  return (
    <Section title="Adjustments">
      {nothing && <p className="text-muted">Nothing to adjust on this booking.</p>}
      {choice === "cancel" && (
        <AdjustForm
          bookingId={booking.id}
          path={`bookings/${booking.id}/cancel`}
          reasonLabel="Why cancel it? The family and the sitter see this."
          submit="Cancel the booking"
          onDone={done}
        />
      )}
      {choice === "refund" && (
        <AdjustForm
          bookingId={booking.id}
          path={`bookings/${booking.id}/refund`}
          amountLabel="Amount to refund (₹)"
          amountHint={`Up to ${rupees(booking.refundable_paise)}.`}
          reasonLabel="Why? The family sees this."
          submit="Refund it"
          onDone={done}
        />
      )}
      {choice === "pay" && (
        <AdjustForm
          bookingId={booking.id}
          path={`bookings/${booking.id}/sitter-pay`}
          amountLabel="Extra pay (₹)"
          amountHint="Up to ₹10,000 at a time. Paid within 12 hours with her other earnings."
          reasonLabel="What's it for? The sitter sees this."
          submit="Add the pay"
          onDone={done}
        />
      )}
      {choice === null && !nothing && (
        <div className="flex flex-wrap gap-3">
          {booking.can_cancel && (
            <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setChoice("cancel")}>
              Cancel the booking
            </Button>
          )}
          {booking.refundable_paise > 0 && (
            <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setChoice("refund")}>
              Refund part
            </Button>
          )}
          {booking.can_add_pay && (
            <Button variant="tertiary" fullWidthOnPhone={false} onClick={() => setChoice("pay")}>
              Add pay for the sitter
            </Button>
          )}
        </div>
      )}
      {booking.can_cancel && choice !== "cancel" && (
        <p className="text-small text-muted">Cancelling refunds anything paid in full. The sitter gets no strike.</p>
      )}
    </Section>
  );
}

function PersonLine({ role, person, to }: { role: string; person: Person; to: string }) {
  return (
    <p className="text-ink">
      {role}: <Link to={to}>{person.full_name ?? person.email}</Link>
      <span className="text-small text-muted"> · {[person.phone, person.email].filter(Boolean).join(" · ")}</span>
    </p>
  );
}

export function AdminBookingPage() {
  const { bookingId = "" } = useParams();
  const booking = useQuery({
    queryKey: bookingKey(bookingId),
    queryFn: () => apiFetch<AdminBooking>(`/admin/bookings/${bookingId}`),
  });

  if (booking.isPending) return <p className="text-center text-muted">Loading…</p>;
  if (booking.isError)
    return (
      <p role="alert" className="text-center text-danger">
        {errorMessage(booking.error)}
      </p>
    );

  const data = booking.data;
  const starts = new Date(data.starts_at);
  const ends = new Date(data.ends_at);
  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <BackLink to="/admin/bookings" label="Bookings" />
      <div>
        <h1>
          {formatDay(starts)}, {formatTime(starts)} to {formatTime(ends)}
        </h1>
        <p className="mt-2 text-muted">
          {adminStatusText(data.status)} · {data.plan.charAt(0).toUpperCase() + data.plan.slice(1)} ·{" "}
          {data.units} {data.units === 1 ? "hour" : "hours"} · {rupees(data.price_paise)}
        </p>
      </div>
      <Section title="Booking">
        <PersonLine role="Family" person={data.parent} to={`/admin/parents/${data.parent.id}`} />
        <PersonLine role="Sitter" person={data.sitter} to={`/admin/sitters/${data.sitter.id}`} />
        {data.children.length > 0 && <p className="text-ink">Children: {data.children.join(", ")}</p>}
        <p className="text-small text-muted">
          Booked {when(data.created_at)}
          {data.checked_in_at ? ` · checked in ${when(data.checked_in_at)}` : ""}
          {data.checked_out_at ? ` · checked out ${when(data.checked_out_at)}` : ""}
          {data.codes_locked ? " · codes locked" : ""}
        </p>
        {data.close_reason && <p className="text-small text-ink">Closed by an admin: {data.close_reason}</p>}
      </Section>
      <Adjustments booking={data} />
      <Section title="Money">
        {data.payments.length === 0 ? (
          <p className="text-muted">Nothing paid or owed yet.</p>
        ) : (
          <ul>
            {data.payments.map((item) => (
              <MoneyRow key={item.id} item={item} bookingId={data.id} />
            ))}
          </ul>
        )}
      </Section>
      <Section title="Sitter's earnings">
        {data.earnings.length === 0 ? (
          <p className="text-muted">Nothing earned for this booking.</p>
        ) : (
          <ul>
            {data.earnings.map((item) => (
              <li key={item.id} className="flex flex-col gap-1 border-t border-line py-3 first:border-t-0">
                <p className="text-ui text-ink">
                  {earningLabel(item)} · {rupees(item.amount_paise)} · {EARNING_STATUS[item.status]}
                </p>
                {item.status === "released" && item.due_by && (
                  <p className="text-small text-muted">Due by {when(item.due_by)}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="What happened">
        <ul>
          {data.history.map((event, index) => (
            <li key={`${event.at}-${index}`} className="border-t border-line py-2 text-small first:border-t-0">
              <span className="text-ink">{adminStatusText(event.action)}</span>
              <span className="text-muted">
                {" "}
                · {event.by ?? "the rules"} · {when(event.at)}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </section>
  );
}
