import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import { ChargePage, type Charge } from "./ChargePage";

// Paying a charge (CLAUDE.md 6.5): UPI details, then the reference; owed until Pacifyco confirms it.

const OWED: Charge = {
  id: "c1",
  kind: "cancellation_charge",
  amount_paise: 139800,
  status: "pending",
  upi_reference: null,
  rejection_reason: null,
  waive_reason: null,
  booking_id: "b1",
  booking_starts_at: kolkataTime("2030-01-07", 9),
  sitter_name: "Lakshmi Nair",
  pay_by_upi: {
    upi_id: "pacifyco@okaxis",
    payee_name: "Pacifyco",
    amount_paise: 139800,
    note: "Pacifyco charge C1",
    upi_link: "upi://pay?pa=pacifyco@okaxis&pn=Pacifyco&am=1398.00&cu=INR&tn=Pacifyco%20charge%20C1",
  },
};

function renderWith(first: Charge, afterSend?: Charge) {
  const posted: unknown[] = [];
  let current = first;
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: JSON.parse(init.body as string) });
      current = afterSend ?? first;
    }
    return Promise.resolve(jsonResponse(current, init?.method === "POST" ? 201 : 200));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/parent/payments/c1"]}>
        <Routes>
          <Route path="/parent/payments/:paymentId" element={<ChargePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Paying a charge", () => {
  test("how to pay, then the reference", async () => {
    const posted = renderWith(OWED, { ...OWED, upi_reference: "555566667777", pay_by_upi: null });
    expect(await screen.findByRole("heading", { name: "Late cancellation charge" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Pay ₹1,398 by UPI" })).toBeTruthy();
    expect(screen.getByText("For the booking with Lakshmi on Mon, 7 Jan, 9:00 am")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Pay in a UPI app" }).getAttribute("href")).toBe(OWED.pay_by_upi!.upi_link);
    fireEvent.change(screen.getByLabelText(/UPI reference/), { target: { value: "5555 6666 7777" } });
    fireEvent.click(screen.getByRole("button", { name: /Send the reference/ }));
    expect(await screen.findByText(/UPI reference 555566667777\. Pacifyco is checking it\./)).toBeTruthy();
    expect(posted).toEqual([
      { url: expect.stringMatching(/\/parent\/payments\/c1\/payment$/), body: { upi_reference: "555566667777" } },
    ]);
  });

  test("a rejected reference says why", async () => {
    renderWith({ ...OWED, rejection_reason: "No such payment arrived." });
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText(/We couldn't confirm your payment: No such payment arrived\./)).toBeTruthy();
  });

  test("waived by Pacifyco", async () => {
    renderWith({ ...OWED, status: "waived", waive_reason: "A family emergency.", pay_by_upi: null });
    expect(await screen.findByText("Pacifyco has waived this charge, so you don't need to pay it.")).toBeTruthy();
    expect(screen.getByText("A family emergency.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /Pay / })).toBeNull();
  });

  test("paid", async () => {
    renderWith({ ...OWED, status: "confirmed", upi_reference: "555566667777", pay_by_upi: null });
    expect(await screen.findByText("Paid. Thank you.")).toBeTruthy();
  });
});
