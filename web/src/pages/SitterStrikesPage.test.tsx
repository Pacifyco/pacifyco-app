import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import { SitterStrikesPage, type SitterStrike, type SitterStrikes } from "./SitterStrikesPage";

// The sitter's strikes (CLAUDE.md 6.5, 6.6): her block, each strike, and a doctor's note for a late
// cancellation.

function renderWith(data: SitterStrikes) {
  vi.mocked(fetch).mockImplementation((() => Promise.resolve(jsonResponse(data))) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SitterStrikesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const LATE: SitterStrike = {
  id: "s1",
  reason: "late_cancellation",
  note: null,
  given_at: kolkataTime("2030-01-05", 10),
  expires_at: kolkataTime("2030-07-06", 10),
  booking_id: "b1",
  booking_starts_at: kolkataTime("2030-01-05", 15),
  removed_at: null,
  removal_reason: null,
  doctor_note_sent: false,
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Your strikes", () => {
  test("blocked: until when, and a doctor's note for a late cancellation", async () => {
    renderWith({ blocked_until: kolkataTime("2030-01-06", 10), counting: 1, strikes: [LATE] });
    expect(await screen.findByText(/You can't take new bookings until Sun, 6 Jan, 10:00 am/)).toBeTruthy();
    expect(screen.getByText("Late cancellation of the booking on Sat, 5 Jan, 3:00 pm")).toBeTruthy();
    expect(screen.getByLabelText(/Were you ill\? Send your doctor's note/)).toBeTruthy();
  });

  test("a note already sent, a removed strike, and one given by Pacifyco", async () => {
    renderWith({
      blocked_until: null,
      counting: 1,
      strikes: [
        { ...LATE, doctor_note_sent: true },
        { ...LATE, id: "s2", removed_at: kolkataTime("2030-01-06", 9), removal_reason: "Doctor's note accepted" },
        { ...LATE, id: "s3", reason: "admin", note: "Rude to a family", booking_starts_at: null },
      ],
    });
    expect(await screen.findByText("Doctor's note sent. Pacifyco is looking at it.")).toBeTruthy();
    expect(screen.getByText("Removed: Doctor's note accepted")).toBeTruthy();
    expect(screen.getByText("Given by Pacifyco")).toBeTruthy();
    expect(screen.getByText("Rude to a family")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull(); // not blocked
  });

  test("none", async () => {
    renderWith({ blocked_until: null, counting: 0, strikes: [] });
    expect(await screen.findByText("No strikes. Thank you for being reliable.")).toBeTruthy();
  });
});
