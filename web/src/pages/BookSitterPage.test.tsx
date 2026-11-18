import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import { BookSitterPage, BookingPage, windowsFrom, type Booking } from "./BookSitterPage";

// "Book this sitter" (CLAUDE.md 6.1 and 6.4): her free times, children, bath time, cameras and a live
// price; her rate, never her plan's name (Reuben, 2026-11-17).

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

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/parent/sitters/:sitterId/book" element={<BookSitterPage />} />
          <Route path="/parent/bookings/:bookingId" element={<BookingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const UNWIND = { per_hour_paise: 69900, extra_child_paise: 15000, one_child_only: false };
const PAUSE = { per_hour_paise: 49900, extra_child_paise: 0, one_child_only: true };
const TIMES = [
  { starts_at: kolkataTime("2030-01-07", 9), ends_at: kolkataTime("2030-01-07", 13) },
  { starts_at: kolkataTime("2030-01-08", 18), ends_at: kolkataTime("2030-01-08", 22) },
];
const CHILDREN = [
  { id: "c1", name: "Asha", date_of_birth: "2025-03-01" },
  { id: "c2", name: "Rohan", date_of_birth: "2027-01-01" },
  { id: "c3", name: "Meera", date_of_birth: "2029-01-01" }, // 12 months old in Jan 2030
];
const BOOKING: Booking = {
  id: "b1",
  sitter_id: "s1",
  sitter_name: "Lakshmi Nair",
  starts_at: kolkataTime("2030-01-07", 9),
  ends_at: kolkataTime("2030-01-07", 11),
  hours: 2,
  children: ["Asha", "Rohan"],
  price_paise: 169800,
  bath_time: true,
  cameras_on: false,
  camera_locations: null,
  status: "pending_payment",
  pay_by: kolkataTime("2030-01-07", 6),
  pay_by_upi: {
    upi_id: "pacifyco@okaxis",
    payee_name: "Pacifyco",
    amount_paise: 169800,
    note: "Pacifyco booking B1",
    upi_link: "upi://pay?pa=pacifyco@okaxis&pn=Pacifyco&am=1698.00&cu=INR&tn=Pacifyco%20booking%20B1",
  },
  payment: null,
};

function api(price = UNWIND, times = TIMES, extra: Record<string, (body: unknown) => Response> = {}) {
  return mockApi({
    "GET /parent/sitters/s1": () => jsonResponse({ id: "s1", full_name: "Lakshmi Nair", plan: "unwind" }),
    "GET /parent/sitters/s1/booking-options": () =>
      jsonResponse({ price, bath_time_allowed: !price.one_child_only, times, first_booking: true, owed_paise: 0 }),
    "GET /parent/children": () => jsonResponse(CHILDREN),
    "POST /parent/bookings": () => jsonResponse(BOOKING, 201),
    "GET /parent/bookings/b1": () => jsonResponse(BOOKING),
    ...extra,
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("times she can be booked", () => {
  test("each free stretch is a day and hours from its midnight", () => {
    expect(windowsFrom(TIMES)).toEqual([
      { day: "2030-01-07", start: 9, end: 13 },
      { day: "2030-01-08", start: 18, end: 22 },
    ]);
    const lateNight = [{ starts_at: kolkataTime("2030-01-07", 22), ends_at: kolkataTime("2030-01-07", 24) }];
    expect(windowsFrom(lateNight)).toEqual([{ day: "2030-01-07", start: 22, end: 24 }]);
  });
});

describe("Book this sitter", () => {
  test("offers her free days and times, and the price follows the choices", async () => {
    api();
    renderAt("/parent/sitters/s1/book");
    expect(await screen.findByRole("heading", { name: "Choose a time with Lakshmi" })).toBeTruthy();
    expect(screen.getByText(/Start with a 1-hour booking/)).toBeTruthy();

    const day = screen.getByLabelText("Day") as HTMLSelectElement;
    expect([...day.options].map((option) => option.text)).toEqual(["Mon 7 Jan", "Tue 8 Jan"]);
    const start = screen.getByLabelText("Start") as HTMLSelectElement;
    expect([...start.options].map((option) => option.text)).toEqual(["9:00 am", "10:00 am", "11:00 am", "12:00 pm (noon)"]);
    const length = screen.getByLabelText("How long") as HTMLSelectElement;
    expect(length.options).toHaveLength(4); // up to 1 pm

    // One child to start; ₹699 an hour.
    expect(screen.getByText("₹699")).toBeTruthy();
    fireEvent.change(length, { target: { value: "2" } });
    expect(screen.getByText("₹1,398")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Rohan"));
    expect(screen.getByText("₹1,698")).toBeTruthy(); // ₹849 an hour for 2 children
    expect(screen.getByText("2 hours × ₹849 an hour for 2 children")).toBeTruthy();
    expect(screen.getByText(/Please pay by Mon, 7 Jan, 6:00 am/)).toBeTruthy();

    // A later start leaves fewer hours.
    fireEvent.change(start, { target: { value: "12" } });
    expect((screen.getByLabelText("How long") as HTMLSelectElement).options).toHaveLength(1);
    fireEvent.change(day, { target: { value: "2030-01-08" } });
    expect((screen.getByLabelText("Start") as HTMLSelectElement).value).toBe("18");

    expect(document.body.textContent).not.toMatch(/Pause|Unwind|Recharge/);
  });

  test("children under 18 months can't be chosen", async () => {
    api();
    renderAt("/parent/sitters/s1/book");
    const baby = (await screen.findByLabelText(/Meera/)) as HTMLInputElement;
    expect(baby.disabled).toBe(true);
    expect(screen.getByText(/looks after children from 18 months/)).toBeTruthy();
  });

  test("sends the booking and shows it waiting for payment", async () => {
    const calls = api();
    renderAt("/parent/sitters/s1/book");
    fireEvent.change(await screen.findByLabelText("How long"), { target: { value: "2" } });
    fireEvent.click(screen.getByLabelText("Rohan"));
    fireEvent.click(screen.getByLabelText("Bath time"));
    fireEvent.click(screen.getByLabelText("Yes"));
    fireEvent.change(screen.getByLabelText("Where are they?"), { target: { value: " Living room " } });
    fireEvent.click(screen.getByRole("button", { name: /Confirm this time/ }));

    expect(await screen.findByRole("heading", { name: "Your booking with Lakshmi" })).toBeTruthy();
    expect(calls.find((call) => call.method === "POST")?.body).toEqual({
      sitter_id: "s1",
      starts_at: kolkataTime("2030-01-07", 9),
      hours: 2,
      child_ids: ["c1", "c2"],
      bath_time: true,
      cameras_on: true,
      camera_locations: "Living room",
    });
    expect(screen.getByText("Waiting for payment")).toBeTruthy();
    expect(screen.getByText("Lakshmi is looking after Asha and Rohan at home, with bath time.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Pay ₹1,698 by UPI" })).toBeTruthy();
  });

  test("asks about cameras before sending", async () => {
    const calls = api();
    renderAt("/parent/sitters/s1/book");
    fireEvent.click(await screen.findByRole("button", { name: /Confirm this time/ }));
    expect(screen.getByText("Please tell us whether cameras are on at home.")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Yes"));
    fireEvent.click(screen.getByRole("button", { name: /Confirm this time/ }));
    expect(screen.getByText("Please tell us where the cameras are.")).toBeTruthy();
    expect(calls.some((call) => call.method === "POST")).toBe(false);
  });

  test("one child at a time, and no bath time, when that's how she works", async () => {
    api(PAUSE);
    renderAt("/parent/sitters/s1/book");
    expect(await screen.findByText("Lakshmi looks after one child at a time.")).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Rohan"));
    expect((screen.getByLabelText("Asha") as HTMLInputElement).checked).toBe(false);
    expect((screen.getByLabelText("Rohan") as HTMLInputElement).checked).toBe(true);
    expect(screen.queryByLabelText("Bath time")).toBeNull();
    expect(screen.getByText("₹499")).toBeTruthy();
  });

  test("shows the API's reason when the time is taken", async () => {
    api(UNWIND, TIMES, {
      "POST /parent/bookings": () =>
        jsonResponse(
          { error: { code: "not_free", message: "She isn't free for all of that time.", details: null } },
          409,
        ),
    });
    renderAt("/parent/sitters/s1/book");
    fireEvent.click(await screen.findByLabelText("No"));
    fireEvent.click(screen.getByRole("button", { name: /Confirm this time/ }));
    await waitFor(() => expect(screen.getByText("She isn't free for all of that time.")).toBeTruthy());
  });

  test.each([
    ["terms_required", "Our terms have changed. Please read and accept them, then you can book.", "/parent/consent"],
    ["outside_service_area", "Pacifyco isn't available in your pin code yet, so bookings can't be made there.", "/parent/details"],
    ["profile_unfinished", "Finish your profile first, then you can book a sitter.", "/parent/profile"],
  ])("when %s stops the booking, it says why and where to fix it", async (code, message, to) => {
    api(UNWIND, TIMES, {
      "GET /parent/sitters/s1/booking-options": () =>
        jsonResponse({ error: { code, message: "From the API.", details: null } }, code === "terms_required" ? 403 : 422),
    });
    renderAt("/parent/sitters/s1/book");
    expect(await screen.findByText(message)).toBeTruthy();
    expect(screen.getByRole("link", { name: /./ }).getAttribute("href")).toBe(to);
  });

  test("money owed: no booking until it's paid", async () => {
    mockApi({
      "GET /parent/sitters/s1": () => jsonResponse({ id: "s1", full_name: "Lakshmi Nair", plan: "unwind" }),
      "GET /parent/sitters/s1/booking-options": () =>
        jsonResponse({ price: UNWIND, bath_time_allowed: true, times: TIMES, first_booking: true, owed_paise: 69900 }),
      "GET /parent/children": () => jsonResponse(CHILDREN),
    });
    renderAt("/parent/sitters/s1/book");
    expect(await screen.findByText(/You owe Pacifyco ₹699\. Please pay it before making a new booking\./)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Your payments" }).getAttribute("href")).toBe("/parent/payments");
    expect(screen.queryByRole("button", { name: /Confirm this time/ })).toBeNull();
  });

  test("no free times: a quiet message and a way back", async () => {
    api(UNWIND, []);
    renderAt("/parent/sitters/s1/book");
    expect(await screen.findByText(/Lakshmi has no free times in the next two weeks/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Find another sitter" })).toBeTruthy();
  });
});

describe("paying for the booking", () => {
  const SENT = { status: "pending", upi_reference: "123456789012", sent_at: BOOKING.starts_at, rejection_reason: null };

  test("shows the UPI ID, a link to pay in a UPI app and a QR code", async () => {
    api();
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
    renderAt("/parent/bookings/b1");
    expect(await screen.findByRole("heading", { name: "Pay ₹1,698 by UPI" })).toBeTruthy();
    expect(screen.getByText("pacifyco@okaxis")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(writeText).toHaveBeenCalledWith("pacifyco@okaxis");
    expect(screen.getByRole("link", { name: "Pay in a UPI app" }).getAttribute("href")).toBe(BOOKING.pay_by_upi!.upi_link);
    const qr = (await screen.findByAltText("QR code to pay ₹1,698 to Pacifyco")) as HTMLImageElement;
    expect(qr.src).toMatch(/^data:image\/svg\+xml/);
    expect(screen.getByText(/Please pay by Mon, 7 Jan, 6:00 am/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Pause|Unwind|Recharge/);
  });

  test("sends the 12-digit UPI reference and shows it being checked", async () => {
    const calls = api(UNWIND, TIMES, {
      "POST /parent/bookings/b1/payment": () => jsonResponse({ ...BOOKING, payment: SENT }, 201),
    });
    renderAt("/parent/bookings/b1");
    const field = await screen.findByLabelText(/UPI reference/);
    fireEvent.change(field, { target: { value: "12345" } });
    fireEvent.click(screen.getByRole("button", { name: /Send the reference/ }));
    expect(screen.getByText("Please enter the 12-digit UPI reference from your UPI app.")).toBeTruthy();
    expect(calls.some((call) => call.method === "POST")).toBe(false);

    fireEvent.change(field, { target: { value: "1234 5678 9012" } });
    fireEvent.click(screen.getByRole("button", { name: /Send the reference/ }));
    expect(await screen.findByRole("heading", { name: "Payment sent" })).toBeTruthy();
    expect(calls.find((call) => call.method === "POST")?.body).toEqual({ upi_reference: "123456789012" });
    expect(screen.getByText(/We're checking your payment of ₹1,698 \(UPI reference 123456789012\)/)).toBeTruthy();
    expect(screen.queryByLabelText(/UPI reference/)).toBeNull();
  });

  test("a rejected payment shows the reason and asks again", async () => {
    api(UNWIND, TIMES, {
      "GET /parent/bookings/b1": () =>
        jsonResponse({ ...BOOKING, payment: { ...SENT, status: "rejected", rejection_reason: "Not received." } }),
    });
    renderAt("/parent/bookings/b1");
    expect(await screen.findByText(/We couldn't confirm your payment: Not received\./)).toBeTruthy();
    expect(screen.getByLabelText(/UPI reference/)).toBeTruthy();
  });

  test("shows the API's reason when the reference can't be taken", async () => {
    api(UNWIND, TIMES, {
      "POST /parent/bookings/b1/payment": () =>
        jsonResponse(
          { error: { code: "upi_reference_used", message: "That UPI reference has already been sent.", details: null } },
          409,
        ),
    });
    renderAt("/parent/bookings/b1");
    fireEvent.change(await screen.findByLabelText(/UPI reference/), { target: { value: "123456789012" } });
    fireEvent.click(screen.getByRole("button", { name: /Send the reference/ }));
    expect(await screen.findByText("That UPI reference has already been sent.")).toBeTruthy();
  });

  test("not paid in time: cancelled, with a way to choose another time", async () => {
    api(UNWIND, TIMES, {
      "GET /parent/bookings/b1": () =>
        jsonResponse({ ...BOOKING, status: "cancelled_unpaid", pay_by_upi: null }),
    });
    renderAt("/parent/bookings/b1");
    expect(await screen.findByText("Cancelled")).toBeTruthy();
    expect(
      screen.getByText(/cancelled because it wasn't paid by Mon, 7 Jan, 6:00 am\. You haven't been charged\./),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Choose another time" }).getAttribute("href")).toBe(
      "/parent/sitters/s1/book",
    );
    expect(screen.queryByRole("heading", { name: /Pay ₹/ })).toBeNull();
  });

  test("another booking was paid for first: cancelled, and a refund if they'd paid", async () => {
    api(UNWIND, TIMES, {
      "GET /parent/bookings/b1": () =>
        jsonResponse({ ...BOOKING, status: "cancelled_slot_taken", pay_by_upi: null, payment: SENT }),
    });
    renderAt("/parent/bookings/b1");
    expect(
      await screen.findByText(/Another booking for this time with Lakshmi was paid for first.*Pacifyco will refund you/),
    ).toBeTruthy();
  });

  test("paid while a child waits for verification: the time is kept", async () => {
    api(UNWIND, TIMES, {
      "GET /parent/bookings/b1": () =>
        jsonResponse({ ...BOOKING, status: "awaiting_verification", pay_by_upi: null, payment: { ...SENT, status: "confirmed" } }),
    });
    renderAt("/parent/bookings/b1");
    expect(await screen.findByText("Paid")).toBeTruthy();
    expect(screen.getByText(/kept this time with Lakshmi for you/)).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /Pay ₹/ })).toBeNull();
  });

  test("confirmed", async () => {
    api(UNWIND, TIMES, {
      "GET /parent/bookings/b1": () => jsonResponse({ ...BOOKING, status: "confirmed", pay_by_upi: null }),
    });
    renderAt("/parent/bookings/b1");
    expect(await screen.findByText("Your booking is confirmed and paid.")).toBeTruthy();
    expect(screen.getByText("Confirmed")).toBeTruthy();
  });

  test("no UPI details yet: says payments aren't open", async () => {
    api(UNWIND, TIMES, { "GET /parent/bookings/b1": () => jsonResponse({ ...BOOKING, pay_by_upi: null }) });
    renderAt("/parent/bookings/b1");
    expect(await screen.findByText("We can't take payments just yet. Please check back soon.")).toBeTruthy();
    expect(screen.queryByLabelText(/UPI reference/)).toBeNull();
  });
});

