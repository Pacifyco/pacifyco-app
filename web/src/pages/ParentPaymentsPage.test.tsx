import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import { ParentPaymentsPage, statusText, type PaymentHistory, type PaymentHistoryItem } from "./ParentPaymentsPage";

// "Your payments" (CLAUDE.md 6.1 and 6.4): payments, charges and refunds; money owed blocks bookings.

function renderWith(history: PaymentHistory) {
  vi.mocked(fetch).mockImplementation((() => Promise.resolve(jsonResponse(history))) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ParentPaymentsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const PAID: PaymentHistoryItem = {
  id: "p1",
  kind: "booking",
  amount_paise: 169800,
  status: "confirmed",
  upi_reference: "123456789012",
  transfer_reference: null,
  rejection_reason: null,
  created_at: kolkataTime("2030-01-06", 20),
  decided_at: kolkataTime("2030-01-06", 21),
  booking_id: "b1",
  booking_starts_at: kolkataTime("2030-01-07", 9),
  sitter_name: "Lakshmi Nair",
};
const REFUND: PaymentHistoryItem = { ...PAID, id: "r1", kind: "refund", status: "pending", upi_reference: null };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Your payments", () => {
  test("lists payments and refunds, each linked to its booking", async () => {
    renderWith({ owed_paise: 0, payments: [REFUND, PAID] });
    const payment = (await screen.findByText("Booking payment")).closest("a")!;
    expect(payment.getAttribute("href")).toBe("/parent/bookings/b1");
    expect(within(payment).getByText("₹1,698")).toBeTruthy();
    expect(within(payment).getByText("Paid")).toBeTruthy();
    expect(within(payment).getByText("With Lakshmi · Mon, 7 Jan, 9:00 am")).toBeTruthy();
    const refund = screen.getByText("Refund").closest("a")!;
    expect(within(refund).getByText("+₹1,698")).toBeTruthy();
    expect(within(refund).getByText("Pacifyco is refunding you")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.body.textContent).not.toMatch(/Pause|Unwind|Recharge/);
  });

  test("money owed is said plainly", async () => {
    renderWith({ owed_paise: 69900, payments: [{ ...PAID, kind: "overtime", status: "pending", amount_paise: 69900 }] });
    expect(await screen.findByText("You owe Pacifyco ₹699. You can't make new bookings until it's paid.")).toBeTruthy();
    expect(screen.getByText("To pay")).toBeTruthy();
  });

  test("nothing yet", async () => {
    renderWith({ owed_paise: 0, payments: [] });
    expect(await screen.findByText("No payments yet. Payments for your bookings will show here.")).toBeTruthy();
  });

  test("each status in the parent's words", () => {
    expect(statusText({ ...PAID, status: "pending" })).toBe("Pacifyco is checking it");
    expect(statusText({ ...PAID, status: "rejected", rejection_reason: "Not received." })).toBe(
      "Not confirmed: Not received.",
    );
    expect(statusText({ ...REFUND, status: "confirmed", transfer_reference: "UTR 4455" })).toBe(
      "Refunded (reference UTR 4455)",
    );
  });
});
