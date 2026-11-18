import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { Toaster } from "../../components/ui";
import { kolkataTime } from "../../lib/times";
import { jsonResponse } from "../../test/renderApp";
import { PaymentsPage, confirmedMessage, type PaymentsQueue } from "./PaymentsPage";

// The admin Payments page (CLAUDE.md 6.1): confirm or reject each UPI payment, pay refunds back.

type Call = { method: string; path: string; body: unknown };

function mockApi(routes: Record<string, (body: unknown) => Response>) {
  const calls: Call[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const method = init?.method ?? "GET";
    const body = init?.body ? (JSON.parse(init.body as string) as unknown) : null;
    calls.push({ method, path, body });
    const handler = routes[`${method} ${path}`];
    return handler ? Promise.resolve(handler(body)) : Promise.reject(new Error(`unexpected ${method} ${path}`));
  }) as typeof fetch);
  return calls;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PaymentsPage />
        <Toaster />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const QUEUE: PaymentsQueue = {
  to_check: [
    {
      id: "p1",
      booking_id: "b1",
      parent_id: "u1",
      parent_name: "Priya Sharma",
      parent_email: "priya@example.com",
      sitter_name: "Lakshmi Nair",
      plan: "unwind",
      starts_at: kolkataTime("2030-01-07", 9),
      hours: 2,
      amount_paise: 169800,
      upi_reference: "123456789012",
      note: "Pacifyco booking B1",
      sent_at: kolkataTime("2030-01-06", 20),
      pay_by: kolkataTime("2030-01-07", 6),
      booking_status: "pending_payment",
      children_verified: false,
    },
  ],
  refunds: [
    {
      id: "r1",
      booking_id: "b2",
      parent_id: "u2",
      parent_name: "Arjun Rao",
      parent_email: "arjun@example.com",
      amount_paise: 99800,
      paid_with_reference: "999999999999",
      owed_since: kolkataTime("2030-01-06", 21),
      booking_status: "cancelled_slot_taken",
    },
  ],
};

const DECIDED = { status: "confirmed", booking_status: "awaiting_verification", refund_owed: false, cancelled_bookings: 1 };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Payments", () => {
  test("lists payments to check with what an admin needs to find them", async () => {
    mockApi({ "GET /admin/payments": () => jsonResponse(QUEUE) });
    renderPage();
    const toCheck = await screen.findByRole("region", { name: "Payments to check" });
    expect(within(toCheck).getByText("₹1,698")).toBeTruthy();
    expect(within(toCheck).getByText("123456789012")).toBeTruthy();
    expect(within(toCheck).getByText("Pacifyco booking B1")).toBeTruthy();
    expect(within(toCheck).getByText("Lakshmi Nair · Unwind")).toBeTruthy(); // admins see the plan
    expect(within(toCheck).getByText(/Not all verified yet/)).toBeTruthy();
    const refunds = screen.getByRole("region", { name: "Refunds to pay" });
    expect(within(refunds).getByText("Pay back ₹998")).toBeTruthy();
    expect(within(refunds).getByText("999999999999")).toBeTruthy();
  });

  test("confirms a payment and says what happened", async () => {
    const calls = mockApi({
      "GET /admin/payments": () => jsonResponse(QUEUE),
      "POST /admin/payments/p1/confirm": () => jsonResponse(DECIDED),
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Confirm received" }));
    expect(
      await screen.findByText(
        "Payment confirmed. The booking is paid and waits for a child's verification. 1 other booking for that time cancelled.",
      ),
    ).toBeTruthy();
    expect(calls.filter((call) => call.method === "GET")).toHaveLength(2); // the queue is fetched again
  });

  test("rejecting needs a reason, which is sent", async () => {
    const calls = mockApi({
      "GET /admin/payments": () => jsonResponse(QUEUE),
      "POST /admin/payments/p1/reject": () =>
        jsonResponse({ status: "rejected", booking_status: "pending_payment", refund_owed: false, cancelled_bookings: 0 }),
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Reject" }));
    fireEvent.click(screen.getByRole("button", { name: "Reject payment" }));
    expect(screen.getByText("Please give a reason. It's shown to the parent.")).toBeTruthy();
    expect(calls.some((call) => call.method === "POST")).toBe(false);
    fireEvent.change(screen.getByLabelText(/Why are you rejecting it/), { target: { value: " Not received " } });
    fireEvent.click(screen.getByRole("button", { name: "Reject payment" }));
    await waitFor(() =>
      expect(calls.find((call) => call.method === "POST")?.body).toEqual({ reason: "Not received" }),
    );
  });

  test("marks a refund paid with its reference", async () => {
    const calls = mockApi({
      "GET /admin/payments": () => jsonResponse(QUEUE),
      "POST /admin/refunds/r1/paid": () => jsonResponse({ status: "confirmed", transfer_reference: "UTR 4455" }),
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Mark refunded" }));
    expect(screen.getByText("Please enter the UPI or bank transfer reference.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Refund reference/), { target: { value: "UTR 4455" } });
    fireEvent.click(screen.getByRole("button", { name: "Mark refunded" }));
    expect(await screen.findByText("Refund recorded. The parent has been told.")).toBeTruthy();
    expect(calls.find((call) => call.method === "POST")?.body).toEqual({ transfer_reference: "UTR 4455" });
  });

  test("shows the API's reason when a payment can't be confirmed", async () => {
    mockApi({
      "GET /admin/payments": () => jsonResponse(QUEUE),
      "POST /admin/payments/p1/confirm": () =>
        jsonResponse(
          { error: { code: "booking_started", message: "This booking's start time has passed.", details: null } },
          409,
        ),
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Confirm received" }));
    expect(await screen.findByText("This booking's start time has passed.")).toBeTruthy();
  });

  test("empty queues say so", async () => {
    mockApi({ "GET /admin/payments": () => jsonResponse({ to_check: [], refunds: [] }) });
    renderPage();
    expect(await screen.findByText("No payments are waiting.")).toBeTruthy();
    expect(screen.getByText("No refunds are owed.")).toBeTruthy();
  });

  test("the toast after confirming names a refund when the time was taken", () => {
    expect(confirmedMessage({ ...DECIDED, booking_status: "cancelled_slot_taken", refund_owed: true })).toBe(
      "Payment recorded. The time was already taken, so a refund is owed.",
    );
    expect(confirmedMessage({ ...DECIDED, booking_status: "confirmed", cancelled_bookings: 0 })).toBe(
      "Payment confirmed. The booking is confirmed.",
    );
  });
});
