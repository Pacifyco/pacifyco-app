import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { earningLabel } from "../lib/earnings";
import { jsonResponse } from "../test/renderApp";
import { SitterEarningsPage, earningStatusText, type SitterEarning, type SitterEarnings } from "./SitterEarningsPage";

// The sitter's earnings (CLAUDE.md 6.10): due, on hold, paid, and each payout.

const PAY: SitterEarning = {
  id: "e1",
  booking_id: "b1",
  booking_starts_at: "2030-01-06T05:30:00Z",
  family_name: "Priya",
  kind: "booking",
  amount_paise: 60_000,
  minutes: 120,
  note: null,
  status: "released",
  due_by: "2030-01-06T20:00:00Z",
  paid_at: null,
};

const DATA: SitterEarnings = {
  held_paise: 10_000,
  due_paise: 60_000,
  paid_paise: 45_000,
  earnings: [
    PAY,
    { ...PAY, id: "e2", booking_id: "b2", kind: "show_up_fee", amount_paise: 10_000, minutes: null, status: "held", due_by: null },
    { ...PAY, id: "e3", booking_id: "b3", amount_paise: 45_000, minutes: 90, status: "paid", paid_at: "2030-01-05T10:00:00Z" },
  ],
  payouts: [{ id: "p1", amount_paise: 45_000, method: "upi", transfer_reference: "555566667777", paid_at: "2030-01-05T10:00:00Z" }],
};

function renderWith(data: SitterEarnings) {
  vi.mocked(fetch).mockImplementation((() => Promise.resolve(jsonResponse(data))) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SitterEarningsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Earnings", () => {
  test("totals, each earning and each payment to her", async () => {
    renderWith(DATA);
    const totals = within(await screen.findByRole("region", { name: "Your totals" }));
    expect(totals.getByText("Due to you").nextSibling?.textContent).toBe("₹600");
    expect(totals.getByText("On hold").nextSibling?.textContent).toBe("₹100");
    expect(totals.getByText("Paid so far").nextSibling?.textContent).toBe("₹450");
    expect(screen.getByText(/Pay is on hold until the booking has ended/)).toBeTruthy();

    const list = within(screen.getByRole("region", { name: "Your earnings" }));
    expect(list.getByText("Booking pay, 2 hours")).toBeTruthy();
    expect(list.getAllByRole("link")[0].getAttribute("href")).toBe("/sitter/bookings/b1");
    expect(list.getByText(/^We'll pay this by /)).toBeTruthy();
    expect(list.getByText("On hold")).toBeTruthy();
    expect(list.getByText(/^Paid /)).toBeTruthy();

    const paid = within(screen.getByRole("region", { name: "Payments to you" }));
    expect(paid.getByText("By UPI · reference 555566667777")).toBeTruthy();
    expect(screen.queryByText(/price|plan/i)).toBeNull();
  });

  test("nothing yet", async () => {
    renderWith({ held_paise: 0, due_paise: 0, paid_paise: 0, earnings: [], payouts: [] });
    expect(await screen.findByText("Nothing yet. Your pay shows here once a booking ends.")).toBeTruthy();
    expect(screen.queryByText(/Pay is on hold/)).toBeNull();
    expect(screen.queryByRole("region", { name: "Payments to you" })).toBeNull();
  });
});

describe("words", () => {
  test("labels and statuses", () => {
    expect(earningLabel({ kind: "overtime", minutes: 60 })).toBe("Overtime, 1 hour");
    expect(earningStatusText({ ...PAY, status: "held", due_by: null })).toBe("On hold");
    expect(earningStatusText(PAY)).toMatch(/^We'll pay this by /);
  });

  test("extra pay from Pacifyco shows its note", async () => {
    renderWith({
      ...DATA,
      earnings: [{ ...PAY, id: "e9", kind: "adjustment", amount_paise: 20_000, minutes: null, note: "Stayed for a storm." }],
    });
    expect(await screen.findByText("Extra pay: Stayed for a storm.")).toBeTruthy();
  });
});
