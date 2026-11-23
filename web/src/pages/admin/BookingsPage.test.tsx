import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../../lib/times";
import { jsonResponse } from "../../test/renderApp";
import { BookingsPage, adminStatusText, type AdminBookingRow } from "./BookingsPage";

// Every booking for admins (phase 10): by group, name and date, 50 at a time.

const ROW: AdminBookingRow = {
  id: "b1",
  starts_at: kolkataTime("2030-01-07", 9),
  ends_at: kolkataTime("2030-01-07", 11),
  status: "confirmed",
  plan: "unwind",
  price_paise: 139_800,
  parent_name: "Priya Rao",
  sitter_name: "Lakshmi Nair",
};

function renderPage(more = false) {
  const urls: string[] = [];
  vi.mocked(fetch).mockImplementation(((url: string) => {
    urls.push(url);
    const page = Number(new URL(url, "http://x").searchParams.get("page") ?? 0);
    const bookings = url.includes("q=") ? [] : [{ ...ROW, id: `b${page + 1}` }];
    return Promise.resolve(jsonResponse({ bookings, more: more && page === 0 }));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/admin/bookings"]}>
        <BookingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return urls;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Bookings, for admins", () => {
  test("each booking opens its page", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: /Mon, 7 Jan, 9:00 am · Priya Rao with Lakshmi Nair/ });
    expect(link.getAttribute("href")).toBe("/admin/bookings/b1");
    expect(link.textContent).toContain("Unwind · ₹1,398 · Confirmed");
  });

  test("filters ask the API", async () => {
    const urls = renderPage();
    await screen.findByRole("link", { name: /Priya Rao/ });
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "past" } });
    await waitFor(() => expect(urls.at(-1)).toMatch(/\/admin\/bookings\?group=past&page=0$/));
    fireEvent.change(screen.getByLabelText("Starting from"), { target: { value: "2030-01-01" } });
    await waitFor(() => expect(urls.at(-1)).toMatch(/group=past&starts_from=2030-01-01&page=0$/));
    fireEvent.change(screen.getByLabelText("Parent's or sitter's name"), { target: { value: "nobody" } });
    expect(await screen.findByText("No bookings match.")).toBeTruthy();
  });

  test("show more loads the next page", async () => {
    renderPage(true);
    await screen.findByRole("link", { name: /Priya Rao/ });
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    await waitFor(() => expect(screen.getAllByRole("link", { name: /Priya Rao/ })).toHaveLength(2));
    expect(screen.queryByRole("button", { name: "Show more" })).toBeNull();
  });

  test("statuses in plain words", () => {
    expect(adminStatusText("cancelled_by_admin")).toBe("Cancelled by admin");
    expect(adminStatusText("in_progress")).toBe("In progress");
  });
});
