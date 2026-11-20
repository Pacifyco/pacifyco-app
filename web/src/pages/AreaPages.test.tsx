import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { AdminHomePage } from "./AreaPages";

// The admin home page's banner for bookings needing a call (CLAUDE.md 6.7): an overdue check-out, or
// codes locked.

function renderWith(needsAttention: unknown[]) {
  vi.mocked(fetch).mockImplementation((() => Promise.resolve(jsonResponse(needsAttention))) as unknown as typeof fetch);
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
});
