import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { AdminHomePage, type AdminDashboard } from "./AreaPages";

// The admin home page (phase 10): a tile for each queue with its count, today's payouts (due now and
// paid today; Reuben, 2026-11-22), the banner for bookings needing a call (CLAUDE.md 6.7) and payouts past
// their 12-hour deadline (6.10).

const NOTHING: AdminDashboard = {
  incidents_open: 0,
  incidents_unresolved: 0,
  sitters_to_review: 0,
  families_to_review: 0,
  payments_to_check: 0,
  refunds_to_pay: 0,
  payouts_due: 0,
  payouts_due_paise: 0,
  payouts_overdue: 0,
  paid_today: 0,
  paid_today_paise: 0,
  reports_open: 0,
  overdue_checkouts: 0,
  issues_open: 0,
  low_ratings: 0,
};

function renderWith(needsAttention: unknown[], payouts = { due: 0, overdue: 0 }, dashboard = NOTHING) {
  vi.mocked(fetch).mockImplementation(((url: string) =>
    Promise.resolve(
      jsonResponse(
        url.endsWith("/admin/payouts/summary") ? payouts : url.endsWith("/admin/dashboard") ? dashboard : needsAttention,
      ),
    )) as unknown as typeof fetch);
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
    await screen.findByRole("list", { name: "What's waiting" });
    expect(screen.queryByText(/past the 12-hour deadline/)).toBeNull();
  });

  test("a tile for each queue, with its count and a link to it", async () => {
    renderWith([], { due: 2, overdue: 1 }, {
      ...NOTHING,
      incidents_open: 1,
      incidents_unresolved: 2,
      sitters_to_review: 1,
      families_to_review: 3,
      payments_to_check: 4,
      refunds_to_pay: 1,
      payouts_due: 2,
      payouts_due_paise: 90_000,
      payouts_overdue: 1,
      paid_today: 3,
      paid_today_paise: 150_000,
      reports_open: 5,
      issues_open: 6,
      low_ratings: 1,
    });
    const tiles = within(await screen.findByRole("list", { name: "What's waiting" }));
    const tile = (label: string) => tiles.getByText(label).closest("a")!;
    expect(tile("Emergencies").textContent).toBe("Emergencies21 not acknowledged");
    expect(tile("Emergencies").getAttribute("href")).toBe("/admin/incidents");
    expect(tile("Verifications").textContent).toBe("Verifications41 sitter · 3 families");
    expect(tile("Payments to check").textContent).toBe("Payments to check41 refund to pay back");
    expect(tile("Payouts due").textContent).toBe("Payouts due₹9001 overdue of 2");
    expect(tile("Paid today").textContent).toBe("Paid today₹1,5003 transfers");
    expect(tile("Reports").getAttribute("href")).toBe("/admin/reports");
    expect(tile("Overdue check-outs").getAttribute("href")).toBe("/admin/overdue-checkouts");
    expect(tile("Issues").textContent).toBe("Issues6Not yet resolved");
    expect(tile("Low ratings").getAttribute("href")).toBe("/admin/ratings");
  });

  test("quiet when nothing is waiting", async () => {
    renderWith([]);
    const tiles = within(await screen.findByRole("list", { name: "What's waiting" }));
    expect(tiles.getByText("Payouts due").closest("a")!.textContent).toBe("Payouts due₹0Nothing due");
    expect(tiles.getByText("Emergencies").closest("a")!.textContent).toBe("Emergencies0None waiting");
  });
});
