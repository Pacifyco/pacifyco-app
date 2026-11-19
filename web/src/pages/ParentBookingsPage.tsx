import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Link, useSearchParams } from "react-router";
import { ButtonLink, Card, EmptyState } from "../components/ui";
import { cx } from "../components/ui/cx";
import { apiFetch } from "../lib/api";
import { formatBookingTime, formatDay, formatTime, joinNames } from "../lib/format";
import { rupees } from "../lib/prices";
import { firstNameOf } from "./FindSittersPage";

// "Your bookings" (CLAUDE.md 6.4; phase 7 "Parent booking lists"): every booking the parent has made,
// upcoming ones soonest first and the rest (ended or cancelled) most recent first, each opening its
// booking page. Never a plan's name. Parent pages have no subheadings, so Upcoming and Past are tabs.

export type BookingListItem = {
  id: string;
  sitter_id: string;
  sitter_name: string | null;
  starts_at: string;
  ends_at: string;
  hours: number;
  children: string[];
  price_paise: number;
  status: string;
  pay_by: string;
  payment_sent: boolean;
};

export type BookingList = { upcoming: BookingListItem[]; past: BookingListItem[] };

/** Where the booking is, in the parent's words. */
export function bookingStatusText(item: BookingListItem): string {
  const sitter = firstNameOf(item.sitter_name);
  switch (item.status) {
    case "requested":
      return `Request sent: waiting for ${sitter}'s answer`;
    case "request_declined":
      return `Not accepted: ${sitter} can't take it`;
    case "request_lapsed":
      return `Not accepted: ${sitter} didn't answer in time`;
    case "pending_payment": {
      if (item.payment_sent) return "Pacifyco is checking your payment";
      const payBy = new Date(item.pay_by);
      return `Accepted: please pay by ${formatDay(payBy)}, ${formatTime(payBy)}`;
    }
    case "awaiting_verification":
      return "Paid: confirmed once every child's birth certificate is checked";
    case "confirmed":
      return "Confirmed";
    case "in_progress":
      return "Happening now";
    case "completed":
      return "Completed";
    case "cancelled_unpaid":
      return "Cancelled: not paid in time";
    case "cancelled_slot_taken":
      return "Cancelled: another booking was confirmed first";
    case "cancelled_unverified":
      return "Cancelled: a child wasn't verified by the start";
    case "cancelled_parent":
      return "Cancelled by you";
    case "cancelled_parent_late":
      return "Cancelled by you, less than 3 hours before: charged";
    case "cancelled_sitter":
    case "cancelled_sitter_late":
      return `Cancelled by ${sitter}`;
    default:
      return item.status.startsWith("cancelled") ? "Cancelled" : "Didn't go ahead";
  }
}

/** Waiting for the parent to pay: the one status that asks something of them. */
function needsYou(item: BookingListItem): boolean {
  return item.status === "pending_payment" && !item.payment_sent;
}

function BookingRow({ item }: { item: BookingListItem }) {
  const sitter = firstNameOf(item.sitter_name);
  return (
    <li className="border-t border-line first:border-t-0">
      <Link to={`/parent/bookings/${item.id}`} className="flex items-center gap-4 py-4 text-ink no-underline">
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-ui">{formatBookingTime(new Date(item.starts_at), new Date(item.ends_at))}</span>
          <span className="text-small text-muted">
            {sitter} with {joinNames(item.children)} · {rupees(item.price_paise)}
          </span>
          <span className={cx("text-small", needsYou(item) ? "text-coral-deep" : "text-muted")}>
            {bookingStatusText(item)}
          </span>
        </span>
        <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
      </Link>
    </li>
  );
}

type Tab = "upcoming" | "past";
const TAB_LABELS: Record<Tab, string> = { upcoming: "Upcoming", past: "Past" };

export function ParentBookingsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("show") === "past" ? "past" : "upcoming";
  const list = useQuery({ queryKey: ["parent", "bookings"], queryFn: () => apiFetch<BookingList>("/parent/bookings") });
  const shown = list.data?.[tab] ?? [];

  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-4">
      <h1>Your bookings</h1>
      <div role="tablist" aria-label="Bookings" className="flex gap-2">
        {(["upcoming", "past"] as const).map((name) => (
          <button
            key={name}
            type="button"
            role="tab"
            aria-selected={tab === name}
            onClick={() => setParams(name === "past" ? { show: "past" } : {}, { replace: true })}
            className={cx(
              "min-h-[44px] rounded-pill border px-5 text-ui transition-colors duration-200 ease-calm",
              tab === name
                ? "border-coral bg-coral text-on-coral"
                : "border-line bg-surface-raised text-ink hover:bg-surface-tint",
            )}
          >
            {TAB_LABELS[name]}
            {list.isSuccess ? ` (${list.data[name].length})` : ""}
          </button>
        ))}
      </div>
      {list.isPending && <p className="text-center text-muted">Loading…</p>}
      {list.isError && (
        <p role="alert" className="text-danger">
          We couldn't load your bookings. Please try again.
        </p>
      )}
      {list.isSuccess &&
        (shown.length === 0 ? (
          tab === "upcoming" ? (
            <EmptyState
              message="No upcoming bookings. When you book a sitter, it will show here."
              action={<ButtonLink to="/parent/sitters">Find a sitter</ButtonLink>}
            />
          ) : (
            <EmptyState message="No past bookings yet." />
          )
        ) : (
          <Card as="section" padding="roomy" role="tabpanel" aria-label={TAB_LABELS[tab]}>
            <ul>
              {shown.map((item) => (
                <BookingRow key={item.id} item={item} />
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}
