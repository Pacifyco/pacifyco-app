import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  parent_id: "p1",
  children: ["Asha"],
  bath_time: true,
  cameras_on: true,
  camera_locations: "Living room",
  outing_where: null,
  pay_paise: 60000,
  status: "confirmed",
  answer_by: null,
  children_details: [
    { name: "Asha", age_months: 40, allergies: "Peanuts", medical_notes: "Inhaler at 6 pm", routines: null },
  ],
  address: "12 MG Road, Koramangala",
  pin_code: "560034",
  emergency_contact: { name: "Ravi Rao", relationship: "Uncle", phone: "+919876543210" },
  report: null,
  buttons_open: false,
  incident: null,
  checked_in_at: null,
  checked_out_at: null,
  codes_locked: false,
  overtime: null,
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

describe("No one's home (6.5)", () => {
  const minutesFromNow = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();
  const NOW: SitterBookingDetail = { ...BOOKING, starts_at: minutesFromNow(-10), ends_at: minutesFromNow(110) };

  function renderWithBooking(first: SitterBookingDetail, after?: SitterBookingDetail) {
    let current = first;
    const posted: { url: string; body: unknown }[] = [];
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted.push({ url, body: init.body ? JSON.parse(init.body as string) : null });
        current = after ?? first;
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

  const OPEN = {
    id: "r1",
    kind: "parent_absent" as const,
    status: "open" as const,
    reported_at: minutesFromNow(-5),
    responded_at: null,
    can_leave_at: minutesFromNow(15),
    decision_note: null,
  };

  test("asks that no child is alone, then reports it", async () => {
    const posted = renderWithBooking(NOW, { ...NOW, report: OPEN });
    fireEvent.click(await screen.findByRole("button", { name: "No one's home" }));
    expect(screen.getByText(/call 112 if you need help/)).toBeTruthy();
    const send = screen.getByRole("button", { name: "Tell Pacifyco no one's home" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("No child is at home without an adult"));
    fireEvent.click(send);
    expect(await screen.findByText(/If no one responds in 1[45] minutes, you may leave\./)).toBeTruthy();
    expect(posted).toEqual([
      { url: expect.stringMatching(/\/sitter\/bookings\/b1\/parent-not-home$/), body: { no_child_alone: true } },
    ]);
  });

  test("after 20 minutes she may leave; if the family responds she waits", async () => {
    renderWithBooking({ ...NOW, report: { ...OPEN, can_leave_at: minutesFromNow(-1) } });
    expect(await screen.findByText("No one has responded, so you may leave. Pacifyco will confirm your show-up fee of ₹200.")).toBeTruthy();
    cleanup();
    renderWithBooking({ ...NOW, report: { ...OPEN, responded_at: minutesFromNow(-1), can_leave_at: null } });
    expect(await screen.findByText("The family has responded and is on the way. Please wait for them.")).toBeTruthy();
  });

  test("only a man at home: she declines, with no strike and ₹100", async () => {
    const declined = { ...OPEN, kind: "only_man_home" as const, can_leave_at: null };
    const posted = renderWithBooking(NOW, { ...NOW, report: declined });
    fireEvent.click(await screen.findByRole("button", { name: "Only a man is at home" }));
    expect(screen.getByText(/You won't get a strike, and once Pacifyco confirms you'll be paid ₹100\./)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Decline this booking" }));
    expect(await screen.findByText(/You've declined this booking/)).toBeTruthy();
    expect(posted.map((call) => call.url)).toEqual([expect.stringMatching(/\/sitter\/bookings\/b1\/only-man-home$/)]);
  });

  test("not before the booking starts", async () => {
    renderWithBooking(BOOKING); // in 2030
    await screen.findByRole("heading", { name: "Meera's family" });
    expect(screen.queryByRole("button", { name: "No one's home" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Only a man is at home" })).toBeNull();
    expect(screen.queryByRole("button", { name: "This child is under 18 months" })).toBeNull();
    expect(screen.queryByRole("button", { name: "I feel unsafe" })).toBeNull();
  });

  test("a child under 18 months: she reports it once an adult is with them", async () => {
    const reported = { ...OPEN, kind: "child_under_age" as const, can_leave_at: null };
    const posted = renderWithBooking(NOW, { ...NOW, report: reported });
    fireEvent.click(await screen.findByRole("button", { name: "This child is under 18 months" }));
    const send = screen.getByRole("button", { name: "Tell Pacifyco" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("An adult is now with the child"));
    fireEvent.click(send);
    expect(await screen.findByText(/Don't leave until an adult is with the child\./)).toBeTruthy();
    expect(posted.map((call) => call)).toEqual([
      { url: expect.stringMatching(/\/sitter\/bookings\/b1\/under-18-months$/), body: { adult_with_child: true } },
    ]);
  });

  test("she feels unsafe: she reports it once the child is with a parent", async () => {
    const reported = { ...OPEN, kind: "sitter_unsafe" as const, can_leave_at: null };
    const posted = renderWithBooking(NOW, { ...NOW, report: reported });
    fireEvent.click(await screen.findByRole("button", { name: "I feel unsafe" }));
    const send = screen.getByRole("button", { name: "Tell Pacifyco and leave" }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("The child is now with a parent"));
    fireEvent.click(send);
    expect(await screen.findByText("We've told Pacifyco and the family. Stay safe.")).toBeTruthy();
    expect(posted.map((call) => call)).toEqual([
      { url: expect.stringMatching(/\/sitter\/bookings\/b1\/unsafe$/), body: { child_with_parent: true } },
    ]);
  });
});

describe("Check-in and check-out (6.7)", () => {
  const minutesFromNow = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();
  const TODAY: SitterBookingDetail = { ...BOOKING, starts_at: minutesFromNow(60), ends_at: minutesFromNow(180) };

  function renderWithBooking(first: SitterBookingDetail, after?: SitterBookingDetail) {
    let current = first;
    const posted: { url: string; body: unknown }[] = [];
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted.push({ url, body: init.body ? JSON.parse(init.body as string) : null });
        current = after ?? first;
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

  beforeEach(() => {
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition: vi.fn((success) => success({ coords: { latitude: 12.9, longitude: 77.6 } })) },
    });
  });

  test("not shown before the day of the booking", async () => {
    renderWithBooking(BOOKING); // starts in 2030
    await screen.findByRole("heading", { name: "Meera's family" });
    expect(screen.queryByRole("button", { name: "Check in" })).toBeNull();
  });

  test("checking in sends the code and her location", async () => {
    const posted = renderWithBooking(TODAY, { ...TODAY, status: "in_progress", checked_in_at: minutesFromNow(0) });
    fireEvent.change(await screen.findByLabelText("Check-in code"), { target: { value: "4821" } });
    fireEvent.click(screen.getByRole("button", { name: "Check in" }));
    expect(await screen.findByRole("button", { name: "Check out" })).toBeTruthy();
    expect(posted).toEqual([
      {
        url: expect.stringMatching(/\/sitter\/bookings\/b1\/check-in$/),
        body: { code: "4821", lat: 12.9, lng: 77.6 },
      },
    ]);
  });

  test("a wrong code shows how many tries are left", async () => {
    vi.mocked(fetch).mockImplementation(((_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        return Promise.resolve(
          jsonResponse(
            { error: { code: "wrong_code", message: "That code's wrong.", details: { attempts_left: 3 } } },
            409,
          ),
        );
      }
      return Promise.resolve(jsonResponse(TODAY));
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
    fireEvent.change(await screen.findByLabelText("Check-in code"), { target: { value: "0000" } });
    fireEvent.click(screen.getByRole("button", { name: "Check in" }));
    expect(await screen.findByText("That code's wrong. 3 tries left.")).toBeTruthy();
  });

  test("locked codes show a message instead of the form", async () => {
    renderWithBooking({ ...TODAY, codes_locked: true });
    expect(await screen.findByText(/Too many wrong codes were entered/)).toBeTruthy();
    expect(screen.queryByLabelText("Check-in code")).toBeNull();
  });

  test("checking out sends the code once she's checked in", async () => {
    const inProgress = { ...TODAY, status: "in_progress" as const, checked_in_at: minutesFromNow(-30) };
    const posted = renderWithBooking(inProgress, { ...inProgress, status: "completed", checked_out_at: minutesFromNow(0) });
    fireEvent.change(await screen.findByLabelText("Check-out code"), { target: { value: "1357" } });
    fireEvent.click(screen.getByRole("button", { name: "Check out" }));
    expect(await screen.findByText("Completed")).toBeTruthy();
    expect(posted).toEqual([
      {
        url: expect.stringMatching(/\/sitter\/bookings\/b1\/check-out$/),
        body: { code: "1357", lat: 12.9, lng: 77.6 },
      },
    ]);
  });
});

describe("Overtime requests (6.8)", () => {
  const minutesFromNow = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();
  const IN_PROGRESS: SitterBookingDetail = {
    ...BOOKING,
    starts_at: minutesFromNow(-90),
    ends_at: minutesFromNow(30),
    status: "in_progress",
    checked_in_at: minutesFromNow(-90),
  };

  function renderWithBooking(first: SitterBookingDetail, after?: SitterBookingDetail) {
    const posted: string[] = [];
    let current = first;
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted.push(url);
        current = after ?? first;
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

  const PENDING = { id: "o1", hours: 2, status: "pending" as const, requested_at: minutesFromNow(-2), decided_at: null };

  test("not shown without a pending request", async () => {
    renderWithBooking(IN_PROGRESS);
    await screen.findByRole("heading", { name: "Meera's family" });
    expect(screen.queryByText(/has asked if you can stay/)).toBeNull();
  });

  test("accepting", async () => {
    const posted = renderWithBooking(
      { ...IN_PROGRESS, overtime: PENDING },
      { ...IN_PROGRESS, overtime: { ...PENDING, status: "accepted", decided_at: minutesFromNow(0) } },
    );
    expect(await screen.findByText(/asked if you can stay 2 more hours/)).toBeTruthy();
    expect(screen.getByText("Nothing is charged now; it's worked out when you check out.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    await vi.waitFor(() => expect(screen.queryByRole("button", { name: "Accept" })).toBeNull());
    expect(posted).toEqual([expect.stringMatching(/\/sitter\/overtime-requests\/o1\/accept$/)]);
  });

  test("declining", async () => {
    const posted = renderWithBooking(
      { ...IN_PROGRESS, overtime: PENDING },
      { ...IN_PROGRESS, overtime: { ...PENDING, status: "declined", decided_at: minutesFromNow(0) } },
    );
    fireEvent.click(await screen.findByRole("button", { name: "Decline" }));
    await vi.waitFor(() => expect(posted).toEqual([expect.stringMatching(/\/sitter\/overtime-requests\/o1\/decline$/)]));
  });
});
