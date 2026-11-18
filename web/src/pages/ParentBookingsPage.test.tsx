import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import { ParentBookingsPage, bookingStatusText, type BookingList, type BookingListItem } from "./ParentBookingsPage";

// "Your bookings" (CLAUDE.md 6.4; phase 7): upcoming and past bookings, each opening its booking page.

function renderWith(list: BookingList, path = "/parent/bookings") {
  vi.mocked(fetch).mockImplementation((() => Promise.resolve(jsonResponse(list))) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <ParentBookingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const UPCOMING: BookingListItem = {
  id: "b1",
  sitter_id: "s1",
  sitter_name: "Lakshmi Nair",
  starts_at: kolkataTime("2030-01-07", 9),
  ends_at: kolkataTime("2030-01-07", 11),
  hours: 2,
  children: ["Asha"],
  price_paise: 139800,
  status: "confirmed",
  pay_by: kolkataTime("2030-01-07", 6),
  payment_sent: false,
};
const PAST: BookingListItem = { ...UPCOMING, id: "b2", status: "cancelled_unpaid" };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Your bookings", () => {
  test("upcoming bookings first, each linked to its booking page", async () => {
    renderWith({ upcoming: [UPCOMING], past: [PAST] });
    const row = (await screen.findByText("Confirmed")).closest("a")!;
    expect(row.getAttribute("href")).toBe("/parent/bookings/b1");
    expect(within(row).getByText("Lakshmi with Asha · ₹1,398")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Upcoming (1)" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByText("Cancelled: not paid in time")).toBeNull();
    expect(document.body.textContent).not.toMatch(/Pause|Unwind|Recharge/);
  });

  test("the Past tab shows ended and cancelled bookings", async () => {
    renderWith({ upcoming: [UPCOMING], past: [PAST] });
    fireEvent.click(await screen.findByRole("tab", { name: "Past (1)" }));
    const row = (await screen.findByText("Cancelled: not paid in time")).closest("a")!;
    expect(row.getAttribute("href")).toBe("/parent/bookings/b2");
    expect(screen.queryByText("Confirmed")).toBeNull();
  });

  test("opens on Past from the link", async () => {
    renderWith({ upcoming: [UPCOMING], past: [PAST] }, "/parent/bookings?show=past");
    expect(await screen.findByText("Cancelled: not paid in time")).toBeTruthy();
  });

  test("nothing booked yet: a way to find a sitter", async () => {
    renderWith({ upcoming: [], past: [] });
    expect(await screen.findByText("No upcoming bookings. When you book a sitter, it will show here.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Find a sitter" }).getAttribute("href")).toBe("/parent/sitters");
  });

  test("statuses in the parent's words", () => {
    expect(bookingStatusText({ ...UPCOMING, status: "pending_payment" })).toBe(
      "Waiting for payment: please pay by Mon, 7 Jan, 6:00 am",
    );
    expect(bookingStatusText({ ...UPCOMING, status: "pending_payment", payment_sent: true })).toBe(
      "Pacifyco is checking your payment",
    );
    expect(bookingStatusText({ ...UPCOMING, status: "awaiting_verification" })).toBe(
      "Paid: confirmed once every child's birth certificate is checked",
    );
    expect(bookingStatusText({ ...UPCOMING, status: "cancelled_slot_taken" })).toBe(
      "Cancelled: another booking was confirmed first",
    );
    expect(bookingStatusText({ ...UPCOMING, status: "cancelled_unverified" })).toBe(
      "Cancelled: a child wasn't verified by the start",
    );
  });
});
