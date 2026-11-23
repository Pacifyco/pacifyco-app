import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ChevronRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { BackLink, Button, Card, Select, TextInput } from "../../components/ui";
import { apiFetch } from "../../lib/api";
import { formatDay, formatTime } from "../../lib/format";
import { rupees } from "../../lib/prices";
import { errorMessage } from "./shared";

// Every booking, for admins (phase 10; Reuben, 2026-11-23): latest start first, 50 at a time, by group,
// name and date. Each opens its admin booking page, where it can be adjusted.

export type AdminBookingRow = {
  id: string;
  starts_at: string;
  ends_at: string;
  status: string;
  plan: "pause" | "unwind" | "recharge";
  price_paise: number;
  parent_name: string | null;
  sitter_name: string | null;
};

type AdminBookingList = { bookings: AdminBookingRow[]; more: boolean };

const GROUP_WORDS = { upcoming: "Upcoming", under_way: "Under way", past: "Past", cancelled: "Cancelled" };

/** Admins see the plan and the raw status, in plain words. */
export function adminStatusText(status: string): string {
  const words = status.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const PLAN_WORDS = { pause: "Pause", unwind: "Unwind", recharge: "Recharge" };

function useDebounced(value: string, delay = 300): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

export function BookingsPage() {
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") ?? "");
  const [pages, setPages] = useState(1);
  const group = params.get("group") ?? "";
  const from = params.get("from") ?? "";
  const to = params.get("to") ?? "";
  const q = useDebounced(text.trim());

  function setFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
    setPages(1);
  }

  const search = new URLSearchParams();
  if (group) search.set("group", group);
  if (q) search.set("q", q);
  if (from) search.set("starts_from", from);
  if (to) search.set("starts_to", to);
  const query = search.toString();
  const pageQueries = Array.from({ length: pages }, (_, page) => page);
  const list = useQuery({
    queryKey: ["admin", "bookings", query, pages],
    queryFn: async () => {
      const found = await Promise.all(
        pageQueries.map((page) =>
          apiFetch<AdminBookingList>(`/admin/bookings?${[query, `page=${page}`].filter(Boolean).join("&")}`),
        ),
      );
      return { bookings: found.flatMap((item) => item.bookings), more: found[found.length - 1].more };
    },
    placeholderData: keepPreviousData,
  });

  return (
    <section className="mx-auto flex max-w-[72ch] flex-col gap-6">
      <BackLink to="/admin" label="Admin" />
      <h1>Bookings</h1>
      <Card padding="roomy" className="flex flex-col gap-4">
        <TextInput
          label="Parent's or sitter's name"
          type="search"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setFilter("q", event.target.value.trim());
          }}
        />
        <Select label="Show" value={group} onChange={(event) => setFilter("group", event.target.value)}>
          <option value="">Every booking</option>
          {(Object.keys(GROUP_WORDS) as (keyof typeof GROUP_WORDS)[]).map((item) => (
            <option key={item} value={item}>
              {GROUP_WORDS[item]}
            </option>
          ))}
        </Select>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TextInput
            label="Starting from"
            type="date"
            value={from}
            onChange={(event) => setFilter("from", event.target.value)}
          />
          <TextInput label="Until" type="date" value={to} onChange={(event) => setFilter("to", event.target.value)} />
        </div>
      </Card>
      {list.isPending && <p className="text-center text-muted">Loading…</p>}
      {list.isError && (
        <p role="alert" className="text-center text-danger">
          {errorMessage(list.error)}
        </p>
      )}
      {list.isSuccess &&
        (list.data.bookings.length === 0 ? (
          <p className="text-center text-muted">No bookings match.</p>
        ) : (
          <Card padding="roomy" className="flex flex-col gap-3">
            <ul aria-label="Bookings">
              {list.data.bookings.map((booking) => {
                const starts = new Date(booking.starts_at);
                return (
                  <li key={booking.id} className="border-t border-line first:border-t-0">
                    <Link
                      to={`/admin/bookings/${booking.id}`}
                      className="flex items-center gap-4 py-4 text-ink no-underline"
                    >
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="text-ui">
                          {formatDay(starts)}, {formatTime(starts)} · {booking.parent_name ?? "A parent"} with{" "}
                          {booking.sitter_name ?? "a sitter"}
                        </span>
                        <span className="truncate text-small text-muted">
                          {PLAN_WORDS[booking.plan]} · {rupees(booking.price_paise)} ·{" "}
                          {adminStatusText(booking.status)}
                        </span>
                      </span>
                      <ChevronRight aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0 text-muted" />
                    </Link>
                  </li>
                );
              })}
            </ul>
            {list.data.more && (
              <div>
                <Button
                  variant="tertiary"
                  fullWidthOnPhone={false}
                  loading={list.isFetching}
                  onClick={() => setPages((count) => count + 1)}
                >
                  Show more
                </Button>
              </div>
            )}
          </Card>
        ))}
    </section>
  );
}
