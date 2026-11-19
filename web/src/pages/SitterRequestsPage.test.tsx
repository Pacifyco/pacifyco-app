import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import type { SitterBookingItem } from "./SitterBookingsPage";
import { SitterRequestsPage } from "./SitterRequestsPage";

// The sitter's requests (CLAUDE.md 6.4): families ask, she answers before they pay.

function renderWith(list: SitterBookingItem[]) {
  vi.mocked(fetch).mockImplementation((() => Promise.resolve(jsonResponse(list))) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SitterRequestsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const REQUEST: SitterBookingItem = {
  id: "b1",
  starts_at: kolkataTime("2030-01-07", 9),
  ends_at: kolkataTime("2030-01-07", 11),
  hours: 2,
  family_name: "Meera",
  children: ["Asha"],
  bath_time: false,
  cameras_on: false,
  camera_locations: null,
  pay_paise: 60000,
  status: "requested",
  answer_by: kolkataTime("2030-01-06", 14),
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Requests", () => {
  test("each request, her pay and when to answer by, opening the request", async () => {
    renderWith([REQUEST]);
    const row = (await screen.findByText("Looking after Asha at Meera's home.")).closest("a")!;
    expect(row.getAttribute("href")).toBe("/sitter/bookings/b1");
    expect(screen.getByText("₹600 for 2 hours")).toBeTruthy();
    expect(screen.getByText("Answer by Sun, 6 Jan, 2:00 pm")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Pause|Unwind|Recharge|plan/i);
  });

  test("none", async () => {
    renderWith([]);
    expect(await screen.findByText("No requests right now. When a family asks to book you, it will show here.")).toBeTruthy();
  });
});
