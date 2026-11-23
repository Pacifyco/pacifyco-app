import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../../test/renderApp";
import { IncidentsPage, type AdminIncident } from "./IncidentsPage";

// Emergencies for admins (CLAUDE.md 6.9). Issues are complaints now (ComplaintsPages.test.tsx).

const INCIDENT: AdminIncident = {
  id: "i1",
  kind: "theft",
  status: "open",
  note: "Bracelet missing",
  raised_by: "parent",
  created_at: "2030-01-07T05:00:00Z",
  suspended_sitter: true,
  sitter_status: "suspended",
  booking_id: "b1",
  starts_at: "2030-01-07T03:30:00Z",
  ends_at: "2030-01-07T05:30:00Z",
  parent_name: "Priya Rao",
  parent_phone: "+919876543210",
  sitter_name: "Lakshmi Nair",
  sitter_phone: "+919812345678",
};

function renderWith(page: ReactNode, list: unknown[]) {
  const posted: { url: string; body: unknown }[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: init.body ? JSON.parse(init.body as string) : null });
      return Promise.resolve(jsonResponse(list[0]));
    }
    return Promise.resolve(jsonResponse(list));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{page}</MemoryRouter>
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Emergencies", () => {
  test("what happened, both numbers, and acknowledging", async () => {
    const posted = renderWith(<IncidentsPage />, [INCIDENT]);
    expect(await screen.findByText(/Theft · from the parent · not acknowledged/)).toBeTruthy();
    expect(screen.getByText(/Bracelet missing/)).toBeTruthy();
    expect(screen.getByText(/suspended by this report/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "+91 98765 43210" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    await vi.waitFor(() => expect(posted.map((call) => call.url)).toEqual([expect.stringMatching(/\/i1\/acknowledge$/)]));
  });

  test("resolving needs a note and can make the sitter active again", async () => {
    const posted = renderWith(<IncidentsPage />, [INCIDENT]);
    fireEvent.click(await screen.findByRole("button", { name: "Resolve" }));
    fireEvent.click(screen.getByRole("button", { name: "Resolve it" }));
    expect(screen.getByText("Please say what happened.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/What happened\?/), { target: { value: "Found at home" } });
    fireEvent.click(screen.getByLabelText("Make the sitter's account active again"));
    fireEvent.click(screen.getByRole("button", { name: "Resolve it" }));
    await vi.waitFor(() =>
      expect(posted).toEqual([
        { url: expect.stringMatching(/\/i1\/resolve$/), body: { note: "Found at home", reinstate_sitter: true } },
      ]),
    );
  });
});
