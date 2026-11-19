import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../../lib/times";
import { jsonResponse } from "../../test/renderApp";
import { StrikesSection, type AdminStrike, type AdminStrikes } from "./StrikesSection";

// A sitter's strikes for admins (CLAUDE.md 6.6): give or remove one with a reason; view a doctor's note.

const STRIKE: AdminStrike = {
  id: "k1",
  reason: "late_cancellation",
  note: null,
  given_at: kolkataTime("2030-01-05", 10),
  expires_at: kolkataTime("2030-07-06", 10),
  booking_id: "b1",
  booking_starts_at: kolkataTime("2030-01-05", 15),
  removed_at: null,
  removal_reason: null,
  doctor_note_sent: true,
  removed_by: null,
  doctor_note_document_id: "d1",
};

function renderWith(data: AdminStrikes, after?: AdminStrikes) {
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
      <StrikesSection sitterId="s1" />
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Strikes for admins", () => {
  test("her block, the strike and the doctor's note", async () => {
    renderWith({ blocked_until: kolkataTime("2030-01-06", 10), counting: 1, strikes: [STRIKE] });
    expect(await screen.findByText(/1 in the last 6 months\. Blocked from new bookings until Sun, 6 Jan, 10:00 am\./)).toBeTruthy();
    expect(screen.getByText(/Late cancellation · Sat, 5 Jan, 10:00 am/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "View doctor's note" })).toBeTruthy();
  });

  test("removing needs a reason, which is sent", async () => {
    const removed = { ...STRIKE, removed_at: kolkataTime("2030-01-06", 9), removal_reason: "Doctor's note accepted" };
    const posted = renderWith(
      { blocked_until: kolkataTime("2030-01-06", 10), counting: 1, strikes: [STRIKE] },
      { blocked_until: null, counting: 0, strikes: [removed] },
    );
    fireEvent.click(await screen.findByRole("button", { name: "Remove this strike" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove the strike" }));
    expect(screen.getByText("Please give a reason; it's shown to the sitter.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Why remove it\?/), { target: { value: "Doctor's note accepted" } });
    fireEvent.click(screen.getByRole("button", { name: "Remove the strike" }));
    expect(await screen.findByText(/Not blocked\./)).toBeTruthy();
    expect(posted).toEqual([{ url: expect.stringMatching(/\/admin\/strikes\/k1\/remove$/), body: { reason: "Doctor's note accepted" } }]);
  });

  test("giving a strike", async () => {
    const posted = renderWith({ blocked_until: null, counting: 0, strikes: [] });
    fireEvent.click(await screen.findByRole("button", { name: "Give a strike" }));
    fireEvent.change(screen.getByLabelText(/Why give a strike\?/), { target: { value: "Rude to a family" } });
    fireEvent.click(screen.getByRole("button", { name: "Give the strike" }));
    await screen.findByRole("button", { name: "Give a strike" });
    expect(posted).toEqual([{ url: expect.stringMatching(/\/admin\/sitters\/s1\/strikes$/), body: { reason: "Rude to a family" } }]);
  });
});
