import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../../lib/times";
import { jsonResponse } from "../../test/renderApp";
import { AdminBookingPage, paiseFrom, type AdminBooking } from "./AdminBookingPage";

// One booking for admins (phase 10): the people, the money, her earnings and what happened, with the
// adjustments (cancel, refund part, add pay, waive a charge), each with a reason.

const BOOKING: AdminBooking = {
  id: "b1",
  status: "confirmed",
  plan: "unwind",
  units: 2,
  children: ["Asha"],
  starts_at: kolkataTime("2030-01-07", 9),
  ends_at: kolkataTime("2030-01-07", 11),
  price_paise: 139_800,
  created_at: kolkataTime("2030-01-05", 10),
  parent: { id: "p1", full_name: "Priya Rao", email: "priya@example.com", phone: "+919876543210" },
  sitter: { id: "s1", full_name: "Lakshmi Nair", email: "lakshmi@example.com", phone: "+919812345678" },
  checked_in_at: null,
  checked_out_at: null,
  codes_locked: false,
  close_reason: null,
  payments: [
    {
      id: "m1",
      kind: "booking",
      amount_paise: 139_800,
      status: "confirmed",
      upi_reference: "123456789012",
      transfer_reference: null,
      rejection_reason: null,
      waive_reason: null,
      created_at: kolkataTime("2030-01-05", 11),
      decided_at: kolkataTime("2030-01-05", 12),
      can_waive: false,
    },
  ],
  earnings: [],
  refundable_paise: 139_800,
  can_cancel: true,
  can_add_pay: false,
  history: [{ action: "payment_confirmed", by: "Asha Admin", at: kolkataTime("2030-01-05", 12), after: null }],
};

function renderWith(data: AdminBooking, after?: AdminBooking) {
  const posted: { url: string; body: unknown }[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: JSON.parse(init.body as string) });
      return Promise.resolve(jsonResponse(after ?? data));
    }
    return Promise.resolve(jsonResponse(data));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/admin/bookings/b1"]}>
        <Routes>
          <Route path="/admin/bookings/:bookingId" element={<AdminBookingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("A booking, for admins", () => {
  test("the people, the money and what happened", async () => {
    renderWith(BOOKING);
    expect(await screen.findByRole("heading", { name: "Mon, 7 Jan, 9:00 am to 11:00 am" })).toBeTruthy();
    expect(screen.getByText(/Confirmed · Unwind · 2 hours · ₹1,398/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Priya Rao" }).getAttribute("href")).toBe("/admin/parents/p1");
    expect(screen.getByRole("link", { name: "Lakshmi Nair" }).getAttribute("href")).toBe("/admin/sitters/s1");
    expect(screen.getByText("Booking payment · ₹1,398 · Done")).toBeTruthy();
    expect(screen.getByText("Payment confirmed")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add pay for the sitter" })).toBeNull();
  });

  test("cancelling needs a reason, which is sent", async () => {
    const posted = renderWith(BOOKING, { ...BOOKING, status: "cancelled_by_admin", can_cancel: false });
    fireEvent.click(await screen.findByRole("button", { name: "Cancel the booking" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel the booking" }));
    expect(screen.getByText("Please give a reason.")).toBeTruthy();
    expect(posted).toEqual([]);
    fireEvent.change(screen.getByLabelText(/Why cancel it\?/), { target: { value: "A fever at home." } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel the booking" }));
    expect(await screen.findByText(/Cancelled by admin · Unwind/)).toBeTruthy();
    expect(posted).toEqual([
      { url: expect.stringMatching(/\/admin\/bookings\/b1\/cancel$/), body: { reason: "A fever at home." } },
    ]);
  });

  test("refunding part sends the amount in paise", async () => {
    const posted = renderWith(BOOKING, { ...BOOKING, refundable_paise: 89_800 });
    fireEvent.click(await screen.findByRole("button", { name: "Refund part" }));
    expect(screen.getByText("Up to ₹1,398.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Amount to refund/), { target: { value: "abc" } });
    fireEvent.change(screen.getByLabelText(/Why\? The family sees this\./), { target: { value: "She was late." } });
    fireEvent.click(screen.getByRole("button", { name: "Refund it" }));
    expect(screen.getByText("Enter an amount in rupees, like 500.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Amount to refund/), { target: { value: "₹500" } });
    fireEvent.click(screen.getByRole("button", { name: "Refund it" }));
    await screen.findByRole("button", { name: "Refund part" });
    expect(posted).toEqual([
      {
        url: expect.stringMatching(/\/admin\/bookings\/b1\/refund$/),
        body: { amount_paise: 50_000, reason: "She was late." },
      },
    ]);
  });

  test("extra pay once it's over, and her earnings", async () => {
    const over: AdminBooking = {
      ...BOOKING,
      status: "completed",
      can_cancel: false,
      can_add_pay: true,
      earnings: [
        {
          id: "e1",
          kind: "adjustment",
          amount_paise: 20_000,
          minutes: null,
          note: "Stayed for a storm.",
          status: "released",
          due_by: kolkataTime("2030-01-07", 23),
        },
      ],
    };
    const posted = renderWith(over);
    expect(await screen.findByText("Extra pay: Stayed for a storm. · ₹200 · Due")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add pay for the sitter" }));
    fireEvent.change(screen.getByLabelText(/Extra pay/), { target: { value: "150" } });
    fireEvent.change(screen.getByLabelText(/What's it for\?/), { target: { value: "Travel" } });
    fireEvent.click(screen.getByRole("button", { name: "Add the pay" }));
    await screen.findByRole("button", { name: "Add pay for the sitter" });
    expect(posted).toEqual([
      { url: expect.stringMatching(/\/admin\/bookings\/b1\/sitter-pay$/), body: { amount_paise: 15_000, reason: "Travel" } },
    ]);
  });

  test("waiving an unpaid charge", async () => {
    const charge = {
      ...BOOKING.payments[0],
      id: "m2",
      kind: "cancellation_charge" as const,
      amount_paise: 69_900,
      status: "pending" as const,
      upi_reference: null,
      can_waive: true,
    };
    const waived = { ...charge, status: "waived" as const, waive_reason: "Goodwill", can_waive: false };
    const posted = renderWith(
      { ...BOOKING, payments: [charge] },
      { ...BOOKING, payments: [waived] },
    );
    fireEvent.click(await screen.findByRole("button", { name: "Waive this charge" }));
    fireEvent.change(screen.getByLabelText(/Why waive it\?/), { target: { value: "Goodwill" } });
    fireEvent.click(screen.getByRole("button", { name: "Waive the charge" }));
    expect(await screen.findByText("Waived: Goodwill")).toBeTruthy();
    expect(posted).toEqual([{ url: expect.stringMatching(/\/admin\/charges\/m2\/waive$/), body: { reason: "Goodwill" } }]);
  });

  test("amounts in rupees", () => {
    expect(paiseFrom("1,398")).toBe(139_800);
    expect(paiseFrom("₹ 12.50")).toBe(1_250);
    expect(paiseFrom("0")).toBeNull();
    expect(paiseFrom("-5")).toBeNull();
    expect(paiseFrom("1.234")).toBeNull();
  });
});
