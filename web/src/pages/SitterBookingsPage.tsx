import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Link, useSearchParams } from "react-router";
import { Card, EmptyState } from "../components/ui";
import { cx } from "../components/ui/cx";
import { apiFetch } from "../lib/api";
import { formatBookingTime, joinNames } from "../lib/format";
import { rupees } from "../lib/prices";

// The sitter's bookings (CLAUDE.md 6.2 and 6.4; phase 7 "Sitter booking lists"): the ones she accepted,
// upcoming soonest first and the rest most recent first. She sees her pay for the booked hours, never
// the price the family paid or the plan's name. What she needs before she goes: who, bath time and the
// family's answer about cameras (6.4). Each opens the booking (`SitterBookingPage`).

export type SitterBookingItem = {
  id: string;
  starts_at: string;
  ends_at: string;
  hours: number;
  family_name: string;
  children: string[];
  bath_time: boolean;
  cameras_on: boolean;
  camera_locations: string | null;
  pay_paise: number;
  status: string;
  answer_by: string | null; // a request: when it lapses unanswered
};

export type SitterBookingList = { upcoming: SitterBookingItem[]; past: SitterBookingItem[] };

/** "Looking after Asha at Meera's home." */
export function sitterBookingLine(item: SitterBookingItem): string {
  return `Looking after ${joinNames(item.children)} at ${item.family_name}'s home.`;
}

/** Where the booking is, in her words. */
export function sitterStatusText(status: string): string {
  switch (status) {
    case "requested":
      return "Request";
    case "request_declined":
      return "You declined";
    case "request_lapsed":
      return "Not answered in time";
    case "pending_payment":
      return "Accepted: waiting for the family to pay";
    case "cancelled_unpaid":
      return "The family didn't pay in time";
    case "confirmed":
      return "Confirmed";
    case "in_progress":
      return "Happening now";
    case "completed":
      return "Completed";
    case "cancelled_parent":
    case "cancelled_parent_late":
      return "Cancelled by the family";
    case "cancelled_sitter":
      return "Cancelled by you";
    case "cancelled_sitter_late":
      return "Cancelled by you, less than 8 hours before: a strike";
    case "parent_absent":
      return "No one was home: show-up fee";
    case "declined_man_at_home":
      return "You declined: only a man was at home";
    case "child_under_age":
      return "Closed: a child was under 18 months";
    case "sitter_left_unsafe":
      return "You left: your safety";
    case "sitter_no_show":
      return "Marked as missed";
    default:
      return "Cancelled";
  }
}

function camerasText(item: SitterBookingItem): string {
  if (!item.cameras_on) return "No cameras on at home.";
  return item.camera_locations ? `Cameras on: ${item.camera_locations}` : "Cameras are on at home.";
}

function BookingRow({ item }: { item: SitterBookingItem }) {
  return (
    <li className="border-t border-line first:border-t-0">
      <Link to={`/sitter/bookings/${item.id}`} className="flex items-center gap-4 py-4 text-ink no-underline">
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-ui text-ink">{formatBookingTime(new Date(item.starts_at), new Date(item.ends_at))}</span>
          <span className="text-small text-ink">
            {sitterBookingLine(item)}
            {item.bath_time ? " Bath time included." : ""}
          </span>
          <span className="text-small text-muted">{camerasText(item)}</span>
          <span className="text-small text-muted">
            {sitterStatusText(item.status)} · {rupees(item.pay_paise)} for{" "}
            {item.hours === 1 ? "1 hour" : `${item.hours} hours`}
          </span>
        </span>
        <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
      </Link>
    </li>
  );
}

type Tab = "upcoming" | "past";
const TAB_LABELS: Record<Tab, string> = { upcoming: "Upcoming", past: "Past" };

export function SitterBookingsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("show") === "past" ? "past" : "upcoming";
  const list = useQuery({ queryKey: ["sitter", "bookings"], queryFn: () => apiFetch<SitterBookingList>("/sitter/bookings") });
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
          <EmptyState
            message={
              tab === "upcoming"
                ? "No upcoming bookings. Confirmed bookings will show here."
                : "No past bookings yet."
            }
          />
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
