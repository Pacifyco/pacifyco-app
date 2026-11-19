import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import { SitterBookingPage, ageText, sitterCancelOutcome, type SitterBookingDetail } from "./SitterBookingPage";

// One of the sitter's bookings (CLAUDE.md 6.4, 6.11): the address once confirmed, the children's care
// notes, cameras, the emergency contact and her pay; never the price.

function renderWith(response: Response) {
  vi.mocked(fetch).mockImplementation((() => Promise.resolve(response)) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/sitter/bookings/b1"]}>
        <Routes>
          <Route path="/sitter/bookings/:bookingId" element={<SitterBookingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const BOOKING: SitterBookingDetail = {
  id: "b1",
  starts_at: kolkataTime("2030-01-07", 9),
  ends_at: kolkataTime("2030-01-07", 11),
  hours: 2,
  family_name: "Meera",
  children: ["Asha"],
  bath_time: true,
  cameras_on: true,
  camera_locations: "Living room",
  pay_paise: 60000,
  status: "confirmed",
  answer_by: null,
  children_details: [
    { name: "Asha", age_months: 40, allergies: "Peanuts", medical_notes: "Inhaler at 6 pm", routines: null },
  ],
  address: "12 MG Road, Koramangala",
  pin_code: "560034",
  emergency_contact: { name: "Ravi Rao", relationship: "Uncle", phone: "+919876543210" },
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("A sitter's booking", () => {
  test("everything she needs before she goes", async () => {
    renderWith(jsonResponse(BOOKING));
    expect(await screen.findByRole("heading", { name: "Meera's family" })).toBeTruthy();
    expect(screen.getByText("12 MG Road, Koramangala")).toBeTruthy();
    expect(screen.getByText("Asha, 3 years")).toBeTruthy();
    expect(screen.getByText("Peanuts")).toBeTruthy();
    expect(screen.getByText("Inhaler at 6 pm")).toBeTruthy();
    expect(screen.getByText("None given")).toBeTruthy(); // routines
    expect(screen.getByText("The family says cameras are on: Living room")).toBeTruthy();
    expect(screen.getByRole("link", { name: "+91 98765 43210" }).getAttribute("href")).toBe("tel:+919876543210");
    expect(screen.getByText("₹600 for 2 hours")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Pause|Unwind|Recharge|plan/i);
  });

  test("past or cancelled: no address or contact", async () => {
    renderWith(jsonResponse({ ...BOOKING, status: "cancelled_parent", address: null, pin_code: null, emergency_contact: null }));
    expect(await screen.findByText("Cancelled by the family")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Where" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Emergency contact" })).toBeNull();
  });

  test("not hers or not confirmed: not found", async () => {
    renderWith(jsonResponse({ error: { code: "not_found", message: "We couldn't find that booking.", details: null } }, 404));
    expect(await screen.findByText("We couldn't find that booking.")).toBeTruthy();
  });

  test("ages", () => {
    expect(ageText(18)).toBe("18 months");
    expect(ageText(30)).toBe("2 years");
  });
});

describe("A request", () => {
  const REQUEST: SitterBookingDetail = {
    ...BOOKING,
    status: "requested",
    answer_by: kolkataTime("2030-01-06", 14),
    address: null,
    emergency_contact: null,
  };

  function renderRequest(after: SitterBookingDetail) {
    const posted: string[] = [];
    let current = REQUEST; // what the API holds: the answered booking once she has answered
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted.push(url);
        current = after;
      }
      return Promise.resolve(jsonResponse(current));
    }) as unknown as typeof fetch);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/sitter/bookings/b1"]}>
          <Routes>
            <Route path="/sitter/bookings/:bookingId" element={<SitterBookingPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    return posted;
  }

  test("everything but the address and contact, and when to answer by", async () => {
    renderRequest(REQUEST);
    expect(await screen.findByText("Answer by Sun, 6 Jan, 2:00 pm")).toBeTruthy();
    expect(screen.getByText("Near 560034. The full address shows once the family has paid.")).toBeTruthy();
    expect(screen.getByText("Peanuts")).toBeTruthy();
    expect(screen.queryByText("12 MG Road, Koramangala")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Emergency contact" })).toBeNull();
    expect(screen.getByRole("link", { name: /Requests/ }).getAttribute("href")).toBe("/sitter/requests");
  });

  test("accepting", async () => {
    const posted = renderRequest({ ...REQUEST, status: "pending_payment", answer_by: null });
    fireEvent.click(await screen.findByRole("button", { name: /Accept/ }));
    expect(await screen.findByText("Accepted: waiting for the family to pay")).toBeTruthy();
    expect(posted).toEqual([expect.stringMatching(/\/sitter\/bookings\/b1\/accept$/)]);
    expect(screen.queryByRole("button", { name: /Accept/ })).toBeNull();
  });

  test("declining", async () => {
    const posted = renderRequest({ ...REQUEST, status: "request_declined", answer_by: null });
    fireEvent.click(await screen.findByRole("button", { name: "Decline" }));
    expect(await screen.findByText("You declined")).toBeTruthy();
    expect(posted).toEqual([expect.stringMatching(/\/sitter\/bookings\/b1\/decline$/)]);
  });
});

describe("She can't make it (6.5)", () => {
  test("8 hours or more before: no penalty; less: a strike", () => {
    const start = new Date(BOOKING.starts_at).getTime();
    expect(sitterCancelOutcome(BOOKING, new Date(start - 8 * 3600_000))).toBe(
      "It's 8 hours or more before the start, so there's no penalty. We'll tell the family and refund them.",
    );
    expect(sitterCancelOutcome(BOOKING, new Date(start - 8 * 3600_000 + 1000))).toMatch(
      /^It's less than 8 hours before the start, so this is a late cancellation: you'll get a strike/,
    );
  });

  test("asks first, then cancels", async () => {
    let current: SitterBookingDetail = BOOKING;
    const posted: string[] = [];
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted.push(url);
        current = { ...BOOKING, status: "cancelled_sitter", address: null, pin_code: null, emergency_contact: null };
      }
      return Promise.resolve(jsonResponse(current));
    }) as unknown as typeof fetch);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/sitter/bookings/b1"]}>
          <Routes>
            <Route path="/sitter/bookings/:bookingId" element={<SitterBookingPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "I can't make this booking" }));
    expect(screen.getByText(/so there's no penalty/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Yes, cancel it" }));
    expect(await screen.findByText("Cancelled by you")).toBeTruthy();
    expect(posted).toEqual([expect.stringMatching(/\/sitter\/bookings\/b1\/cancel$/)]);
    expect(screen.queryByRole("button", { name: "I can't make this booking" })).toBeNull();
  });
});
