import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../../lib/times";
import { jsonResponse } from "../../test/renderApp";
import { AuditLogPage, valueText, type AuditEntry } from "./AuditLogPage";

// The audit log, for admins (phase 10): who did what to which record, newest first, 50 at a time.

const LEVEL_SET: AuditEntry = {
  id: 2,
  at: kolkataTime("2030-01-07", 9),
  by: "Asha Admin",
  by_id: "a1",
  action: "sitter_level_set",
  entity: "sitters",
  entity_id: "s1",
  person: { id: "s1", full_name: "Lakshmi Nair", role: "sitter" },
  before: { level: null },
  after: { level: "pause" },
};

const CANCELLED: AuditEntry = {
  id: 1,
  at: kolkataTime("2030-01-07", 8),
  by: null,
  by_id: null,
  action: "booking_cancelled",
  entity: "booking",
  entity_id: "b1",
  person: null,
  before: { status: "pending_payment" },
  after: { status: "cancelled_unpaid", amount_paise: 139_800 },
};

function renderPage(more = false) {
  const urls: string[] = [];
  vi.mocked(fetch).mockImplementation(((url: string) => {
    if (url.includes("/admin/audit-log")) urls.push(url);
    if (url.endsWith("/admin/admins")) return Promise.resolve(jsonResponse([{ id: "a1", full_name: "Asha Admin" }]));
    const page = Number(new URL(url, "http://x").searchParams.get("page") ?? 0);
    const entries = url.includes("action=") ? [] : page === 0 ? [LEVEL_SET] : [CANCELLED];
    return Promise.resolve(jsonResponse({ entries, more: more && page === 0 }));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/admin/audit-log"]}>
        <AuditLogPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return urls;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("The audit log", () => {
  test("each entry: what, about whom, who and when, and what changed", async () => {
    renderPage(true);
    expect(await screen.findByText("Sitter level set")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Lakshmi Nair" }).getAttribute("href")).toBe("/admin/sitters/s1");
    expect(screen.getByText("Asha Admin · Mon, 7 Jan, 9:00 am")).toBeTruthy();
    expect(screen.getByText("Level: none → pause")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(await screen.findByText("Booking cancelled")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Booking" }).getAttribute("href")).toBe("/admin/bookings/b1");
    expect(screen.getByText("The rules · Mon, 7 Jan, 8:00 am")).toBeTruthy();
    expect(screen.getByText("Amount paise: ₹1,398")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  test("filters ask the API", async () => {
    const urls = renderPage();
    await screen.findByText("Sitter level set");
    await screen.findByRole("option", { name: "Asha Admin" });
    fireEvent.change(screen.getByLabelText("Done by"), { target: { value: "rules" } });
    await waitFor(() => expect(urls.at(-1)).toMatch(/\/admin\/audit-log\?by=rules&page=0$/));
    fireEvent.change(screen.getByLabelText("Kind of record"), { target: { value: "payment" } });
    await waitFor(() => expect(urls.at(-1)).toMatch(/by=rules&entity=payment&page=0$/));
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2030-01-01" } });
    await waitFor(() => expect(urls.at(-1)).toMatch(/entity=payment&on_from=2030-01-01&page=0$/));
    fireEvent.change(screen.getByLabelText(/Record id/), { target: { value: " b1 " } });
    await waitFor(() => expect(urls.at(-1)).toMatch(/entity_id=b1&on_from/));
    fireEvent.change(screen.getByLabelText(/What happened/), { target: { value: "refund" } });
    expect(await screen.findByText("Nothing matches.")).toBeTruthy();
    expect(urls.at(-1)).toMatch(/action=refund/);
  });

  test("values in plain words", () => {
    expect(valueText("status", null)).toBe("none");
    expect(valueText("refund_paise", -50_000)).toMatch(/500/);
    expect(valueText("locked", true)).toBe("yes");
    expect(valueText("hours", 2)).toBe("2");
  });
});
