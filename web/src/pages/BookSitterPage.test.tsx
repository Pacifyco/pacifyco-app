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
};

function api(price = UNWIND, times = TIMES, extra: Record<string, (body: unknown) => Response> = {}) {
  return mockApi({
    "GET /parent/sitters/s1": () => jsonResponse({ id: "s1", full_name: "Lakshmi Nair", plan: "unwind" }),
    "GET /parent/sitters/s1/booking-options": () =>
      jsonResponse({ price, bath_time_allowed: !price.one_child_only, times, first_booking: true }),
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

  test("no free times: a quiet message and a way back", async () => {
    api(UNWIND, []);
    renderAt("/parent/sitters/s1/book");
    expect(await screen.findByText(/Lakshmi has no free times in the next two weeks/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Find another sitter" })).toBeTruthy();
  });
});
