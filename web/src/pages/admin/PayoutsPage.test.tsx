import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../../test/renderApp";
import { PayoutsPage, countdown, earningLabel, type DueEarning, type SitterDue } from "./PayoutsPage";

// Payouts due (CLAUDE.md 6.10): by sitter, soonest deadline first, with a countdown to each deadline.

const minutesFromNow = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();

const PAY: DueEarning = {
  id: "e1",
  booking_id: "b1",
  booking_starts_at: "2030-01-06T05:30:00Z",
  kind: "booking",
  amount_paise: 60_000,
  minutes: 120,
  due_by: minutesFromNow(-25),
};

const OVERDUE: SitterDue = {
  sitter_id: "s1",
  sitter_name: "Lakshmi Nair",
  sitter_phone: "+919812345678",
  payout_method: "bank",
  upi_id: null,
  bank: { account_holder_name: "Lakshmi Nair", account_number: "123456789012", ifsc_code: "HDFC0001234" },
  total_paise: 90_000,
  next_due_by: PAY.due_by,
  earnings: [PAY, { ...PAY, id: "e2", kind: "overtime", amount_paise: 30_000, minutes: 60, due_by: minutesFromNow(-25) }],
};

const DUE_LATER: SitterDue = {
  ...OVERDUE,
  sitter_id: "s2",
  sitter_name: "Asha Menon",
  payout_method: "upi",
  upi_id: "asha@okaxis",
  bank: null,
  total_paise: 10_000,
  next_due_by: minutesFromNow(700),
  earnings: [{ ...PAY, id: "e3", booking_id: "b2", kind: "show_up_fee", amount_paise: 10_000, minutes: null, due_by: minutesFromNow(700) }],
};

function renderWith(list: SitterDue[]) {
  const posted: { url: string; body: unknown }[] = [];
  let current = list;
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: JSON.parse(init.body as string) });
      current = list.slice(1);
      return Promise.resolve(jsonResponse({ id: "p1" }));
    }
    return Promise.resolve(jsonResponse(current));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PayoutsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Payouts due", () => {
  test("each sitter, with how to pay her and a countdown; overdue ones stand out", async () => {
    renderWith([OVERDUE, DUE_LATER]);
    expect(await screen.findByText("Lakshmi Nair", { selector: "p" })).toBeTruthy();
    expect(screen.getByText("₹900")).toBeTruthy();
    expect(screen.getByText(/^Overdue by 2[56] min$/, { selector: "p" }).className).toContain("text-danger");
    expect(screen.getByText("123456789012")).toBeTruthy();
    expect(screen.getByText("HDFC0001234")).toBeTruthy();
    const hers = within(screen.getByRole("list", { name: "Due to Lakshmi Nair" }));
    expect(hers.getByText(/Booking pay, 2 hours · booking/)).toBeTruthy();
    expect(hers.getByText(/Overtime, 1 hour · booking/)).toBeTruthy();

    expect(screen.getByText("UPI: asha@okaxis")).toBeTruthy();
    expect(screen.getByText(/^Due in 11 h (39|40) min$/, { selector: "p" })).toBeTruthy();
    expect(screen.getByText(/Show-up fee · booking/)).toBeTruthy();
  });

  test("mark paid: the reference, for exactly the earnings shown", async () => {
    const posted = renderWith([OVERDUE, DUE_LATER]);
    const card = (await screen.findByText("Lakshmi Nair", { selector: "p" })).closest("li")!;
    fireEvent.click(within(card).getByRole("button", { name: "Mark paid" }));
    fireEvent.click(within(card).getByRole("button", { name: "Mark ₹900 paid" }));
    expect(within(card).getByText("Enter the UPI reference or bank transfer reference (UTR).")).toBeTruthy();
    fireEvent.change(within(card).getByLabelText(/Transfer reference/), { target: { value: " HDFC0000123456 " } });
    fireEvent.click(within(card).getByRole("button", { name: "Mark ₹900 paid" }));
    await vi.waitFor(() =>
      expect(posted).toEqual([
        {
          url: expect.stringMatching(/\/admin\/payouts\/s1\/paid$/),
          body: { earning_ids: ["e1", "e2"], transfer_reference: "HDFC0000123456" },
        },
      ]),
    );
    await vi.waitFor(() => expect(screen.queryByText("Lakshmi Nair", { selector: "p" })).toBeNull());
  });

  test("no payout details: call her first", async () => {
    renderWith([{ ...DUE_LATER, payout_method: null, upi_id: null }]);
    expect(await screen.findByText("No payout details. Call her before paying.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mark paid" })).toBeNull();
  });

  test("nothing due", async () => {
    renderWith([]);
    expect(await screen.findByText("Nothing to pay right now.")).toBeTruthy();
  });
});

describe("countdowns and labels", () => {
  const now = new Date("2030-01-06T06:00:00Z");
  test("due in, or overdue by", () => {
    expect(countdown("2030-01-06T17:40:00Z", now)).toEqual({ text: "Due in 11 h 40 min", overdue: false });
    expect(countdown("2030-01-06T07:00:00Z", now)).toEqual({ text: "Due in 1 h", overdue: false });
    expect(countdown("2030-01-06T05:35:00Z", now)).toEqual({ text: "Overdue by 25 min", overdue: true });
  });

  test("what each earning is for", () => {
    expect(earningLabel({ ...PAY, minutes: 90 })).toBe("Booking pay, 1 hour 30 min");
    expect(earningLabel({ ...PAY, kind: "show_up_fee", minutes: null })).toBe("Show-up fee");
  });
});
