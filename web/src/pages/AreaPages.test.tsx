import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { AdminHomePage } from "./AreaPages";

// The admin home page's banner for bookings needing a call (CLAUDE.md 6.7): an overdue check-out, or
// codes locked. And payouts past their 12-hour deadline (6.10).

function renderWith(needsAttention: unknown[], payouts = { due: 0, overdue: 0 }) {
  vi.mocked(fetch).mockImplementation(((url: string) =>
    Promise.resolve(jsonResponse(url.endsWith("/admin/payouts/summary") ? payouts : needsAttention))) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AdminHomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Admin home", () => {
  test("no banner when nothing needs attention", async () => {
    renderWith([]);
    await screen.findByRole("heading", { name: "Admin" });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("a banner with the count once something does", async () => {
    renderWith([{}, {}]);
    expect(await screen.findByText("2 bookings need a call: an overdue check-out, or codes locked.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open overdue check-outs" }).getAttribute("href")).toBe(
      "/admin/overdue-checkouts",
    );
  });

  test("singular wording for one", async () => {
    renderWith([{}]);
    expect(await screen.findByText("1 booking needs a call: an overdue check-out, or codes locked.")).toBeTruthy();
  });

  test("a banner when payouts are past the 12-hour deadline", async () => {
    renderWith([], { due: 3, overdue: 2 });
    expect(await screen.findByText(/2 payouts are past the 12-hour deadline\./)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open payouts" }).getAttribute("href")).toBe("/admin/payouts");
  });

  test("no payouts banner when nothing is overdue", async () => {
    renderWith([], { due: 3, overdue: 0 });
    await screen.findByRole("link", { name: "Payouts" });
    expect(screen.queryByText(/past the 12-hour deadline/)).toBeNull();
  });
});
