import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../../test/renderApp";
import { RatingsPage, type RatingFlag } from "./RatingsPage";

// Low ratings (CLAUDE.md 6.11): tell her the reason, read her response, close with a note.

const FLAG: RatingFlag = {
  id: "f1",
  sitter_id: "s1",
  sitter_name: "Lakshmi Nair",
  sitter_phone: "+919876543210",
  average: 2.2,
  reviews_counted: 5,
  status: "open",
  created_at: "2026-11-20T10:00:00Z",
  reason: null,
  told_at: null,
  response: null,
  responded_at: null,
  respond_by: null,
  can_close: true,
};

function renderWith(flags: RatingFlag[]) {
  const calls: { method: string; path: string; body: unknown }[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const method = init?.method ?? "GET";
    calls.push({ method, path, body: init?.body ? (JSON.parse(init.body as string) as unknown) : null });
    return Promise.resolve(jsonResponse(method === "GET" ? flags : flags[0]));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RatingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return calls;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Low ratings", () => {
  test("nothing flagged", async () => {
    renderWith([]);
    expect(await screen.findByText("No sitters flagged for low ratings.")).toBeTruthy();
  });

  test("a new flag: tell her the reason", async () => {
    const calls = renderWith([FLAG]);
    expect(await screen.findByText("2.2 over her last 5 reviews")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Lakshmi Nair" }).getAttribute("href")).toBe("/admin/sitters/s1");
    fireEvent.click(screen.getByRole("button", { name: "Tell her" }));
    expect(await screen.findByText("Tell her the reason.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Tell her the reason/), { target: { value: " On her phone " } });
    fireEvent.click(screen.getByRole("button", { name: "Tell her" }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "POST", path: "/admin/rating-flags/f1/tell", body: { reason: "On her phone" } }),
    );
  });

  test("her response, then close with a note", async () => {
    const answered: RatingFlag = {
      ...FLAG,
      status: "responded",
      reason: "On her phone",
      told_at: "2026-11-21T10:00:00Z",
      response: "The parent was calling me.",
      responded_at: "2026-11-22T10:00:00Z",
      respond_by: "2030-01-05T22:00:00Z",
    };
    const calls = renderWith([answered]);
    const list = within(await screen.findByRole("region", { name: "Flagged sitters" }));
    expect(list.getByText("On her phone")).toBeTruthy();
    expect(list.getByText("The parent was calling me.")).toBeTruthy();
    fireEvent.change(list.getByLabelText(/Close with a note/), { target: { value: "Keeping her." } });
    fireEvent.click(list.getByRole("button", { name: "Close the flag" }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "POST", path: "/admin/rating-flags/f1/close", body: { note: "Keeping her." } }),
    );
  });

  test("told: no closing until she responds or her 12 hours pass", async () => {
    const told = {
      ...FLAG,
      status: "told" as const,
      reason: "On her phone",
      told_at: "2026-11-21T10:00:00Z",
      respond_by: "2030-01-05T22:00:00Z",
      can_close: false,
    };
    renderWith([told]);
    expect(await screen.findByText("Waiting for her response. She has until Sun, 6 Jan, 3:30 am.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Close the flag" })).toBeNull();
    cleanup();
    renderWith([{ ...told, can_close: true }]);
    expect(await screen.findByText("She didn't respond within 12 hours.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Close the flag" })).toBeTruthy();
  });
});
