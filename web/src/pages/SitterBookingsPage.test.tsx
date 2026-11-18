import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import {
  SitterBookingsPage,
  sitterStatusText,
  type SitterBookingItem,
  type SitterBookingList,
} from "./SitterBookingsPage";

// The sitter's bookings (CLAUDE.md 6.2, 6.4; phase 7): confirmed ones only, her pay, never the price.

function renderWith(list: SitterBookingList, path = "/sitter/bookings") {
  vi.mocked(fetch).mockImplementation((() => Promise.resolve(jsonResponse(list))) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <SitterBookingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const NEXT: SitterBookingItem = {
  id: "b1",
  starts_at: kolkataTime("2030-01-07", 9),
  ends_at: kolkataTime("2030-01-07", 11),
  hours: 2,
  family_name: "Meera",
  children: ["Asha", "Rohan"],
  bath_time: true,
  cameras_on: true,
  camera_locations: "Living room",
  pay_paise: 60000,
  status: "confirmed",
};
const DONE: SitterBookingItem = { ...NEXT, id: "b2", status: "cancelled_parent", bath_time: false, cameras_on: false };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("The sitter's bookings", () => {
  test("upcoming: who, bath time, cameras and her pay", async () => {
    renderWith({ upcoming: [NEXT], past: [DONE] });
    expect(await screen.findByText(/Looking after Asha and Rohan at Meera's home\. Bath time included\./)).toBeTruthy();
    expect(screen.getByText("Cameras on: Living room")).toBeTruthy();
    expect(screen.getByText("Confirmed · ₹600 for 2 hours")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Upcoming (1)" }).getAttribute("aria-selected")).toBe("true");
    expect(document.body.textContent).not.toMatch(/Pause|Unwind|Recharge|plan/i);
  });

  test("the Past tab", async () => {
    renderWith({ upcoming: [NEXT], past: [DONE] });
    fireEvent.click(await screen.findByRole("tab", { name: "Past (1)" }));
    expect(await screen.findByText("Cancelled by the family · ₹600 for 2 hours")).toBeTruthy();
    expect(screen.getByText("No cameras on at home.")).toBeTruthy();
  });

  test("nothing yet", async () => {
    renderWith({ upcoming: [], past: [] });
    expect(await screen.findByText("No upcoming bookings. Confirmed bookings will show here.")).toBeTruthy();
  });

  test("statuses in her words", () => {
    expect(sitterStatusText("in_progress")).toBe("Happening now");
    expect(sitterStatusText("cancelled_sitter_late")).toBe("Cancelled by you");
    expect(sitterStatusText("parent_absent")).toBe("The family wasn't home");
  });
});
