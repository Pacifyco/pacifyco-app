import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../../test/renderApp";
import { ReportsPage, waitText, type AdminReport } from "./ReportsPage";

// Reports for admins (CLAUDE.md 6.5): call both, then mark answered, confirm or dismiss.

const minutesFromNow = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();

const REPORT: AdminReport = {
  id: "r1",
  kind: "parent_absent",
  reported_at: minutesFromNow(-8),
  responded_at: null,
  can_leave_at: minutesFromNow(12),
  booking_id: "b1",
  starts_at: minutesFromNow(-10),
  ends_at: minutesFromNow(110),
  hours: 2,
  parent_name: "Priya Rao",
  parent_phone: "+919876543210",
  sitter_name: "Lakshmi Nair",
  sitter_phone: "+919812345678",
  show_up_fee_paise: 20000,
};

function renderWith(list: AdminReport[]) {
  const posted: { url: string; body: unknown }[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: JSON.parse(init.body as string) });
      return Promise.resolve(jsonResponse(list[0]));
    }
    return Promise.resolve(jsonResponse(list));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Reports", () => {
  test("what happened, the countdown and both phone numbers", async () => {
    renderWith([REPORT]);
    expect(await screen.findByText("No one home, says the sitter")).toBeTruthy();
    expect(screen.getByText(/No response yet\. She may leave in 1[12] minutes\./)).toBeTruthy();
    expect(screen.getByRole("link", { name: "+91 98765 43210" }).getAttribute("href")).toBe("tel:+919876543210");
    expect(screen.getByRole("link", { name: "+91 98123 45678" })).toBeTruthy();
  });

  test("the parent answered", async () => {
    const posted = renderWith([REPORT]);
    fireEvent.click(await screen.findByRole("button", { name: "The parent answered" }));
    await screen.findByText("No one home, says the sitter");
    await vi.waitFor(() => expect(posted.map((call) => call.url)).toEqual([expect.stringMatching(/\/admin\/reports\/r1\/answered$/)]));
  });

  test("dismissing needs a reason", async () => {
    const posted = renderWith([REPORT]);
    fireEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss it" }));
    expect(screen.getByText("Please say why you're dismissing it.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Why are you dismissing it\?/), { target: { value: "Parent was in the garden" } });
    fireEvent.click(screen.getByRole("button", { name: "Dismiss it" }));
    await vi.waitFor(() =>
      expect(posted).toEqual([{ url: expect.stringMatching(/\/r1\/dismiss$/), body: { note: "Parent was in the garden" } }]),
    );
  });

  test("the wait, in words", () => {
    const now = new Date();
    expect(waitText({ ...REPORT, can_leave_at: minutesFromNow(-1) }, now)).toBe(
      "No response in 20 minutes: she may leave. Confirming pays her ₹200.",
    );
    expect(waitText({ ...REPORT, responded_at: minutesFromNow(-2) }, now)).toMatch(/^A parent responded/);
    expect(waitText({ ...REPORT, kind: "sitter_no_show" }, now)).toBeNull();
    expect(waitText({ ...REPORT, kind: "only_man_home", show_up_fee_paise: 10000 }, now)).toBe(
      "She has declined and left. Confirming closes the booking, charged in full, and pays her ₹100.",
    );
  });

  test("none", async () => {
    renderWith([]);
    expect(await screen.findByText("No reports waiting.")).toBeTruthy();
  });
});
