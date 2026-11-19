import { useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { Link } from "react-router";
import { Card, EmptyState } from "../components/ui";
import { apiFetch } from "../lib/api";
import { formatBookingTime, formatDay, formatTime } from "../lib/format";
import { rupees } from "../lib/prices";
import { sitterBookingLine, type SitterBookingItem } from "./SitterBookingsPage";

// The sitter's requests (CLAUDE.md 6.4; Reuben, 2026-11-19): families ask, she accepts or declines before
// they pay. She sees a request once every child on it is verified, and has 5 hours to answer (less if
// the booking is soon). Each opens the request, where she answers.

/** "Answer by Mon 7 Jan, 2:00 pm". */
export function answerByText(item: SitterBookingItem): string {
  if (!item.answer_by) return "";
  const by = new Date(item.answer_by);
  return `Answer by ${formatDay(by)}, ${formatTime(by)}`;
}

export function SitterRequestsPage() {
  const list = useQuery({
    queryKey: ["sitter", "requests"],
    queryFn: () => apiFetch<SitterBookingItem[]>("/sitter/requests"),
  });

  return (
    <section className="mx-auto flex max-w-[62ch] flex-col gap-4">
      <h1>Requests</h1>
      {list.isPending && <p className="text-center text-muted">Loading…</p>}
      {list.isError && (
        <p role="alert" className="text-danger">
          We couldn't load your requests. Please try again.
        </p>
      )}
      {list.isSuccess &&
        (list.data.length === 0 ? (
          <EmptyState message="No requests right now. When a family asks to book you, it will show here." />
        ) : (
          <Card as="section" padding="roomy">
            <ul>
              {list.data.map((item) => (
                <li key={item.id} className="border-t border-line first:border-t-0">
                  <Link
                    to={`/sitter/bookings/${item.id}`}
                    className="flex items-center gap-4 py-4 text-ink no-underline"
                  >
                    <span className="flex min-w-0 flex-1 flex-col gap-1">
                      <span className="text-ui">
                        {formatBookingTime(new Date(item.starts_at), new Date(item.ends_at))}
                      </span>
                      <span className="text-small text-ink">{sitterBookingLine(item)}</span>
                      <span className="text-small text-muted">
                        {rupees(item.pay_paise)} for {item.hours === 1 ? "1 hour" : `${item.hours} hours`}
                      </span>
                      <span className="text-small text-coral-deep">{answerByText(item)}</span>
                    </span>
                    <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        ))}
    </section>
  );
}
