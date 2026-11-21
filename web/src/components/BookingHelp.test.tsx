import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { BookingHelp, type BookingIncident } from "./BookingHelp";

// The Emergency and Issues buttons (CLAUDE.md 6.9).

function renderHelp(role: "parent" | "sitter", buttonsOpen = true, incident: BookingIncident | null = null) {
  const posted: { url: string; body: unknown }[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    posted.push({ url, body: init?.body ? JSON.parse(init.body as string) : null });
    return Promise.resolve(jsonResponse({}, 201));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <BookingHelp role={role} bookingId="b1" buttonsOpen={buttonsOpen} incident={incident} queryKey={["booking", "b1"]} />
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Emergency", () => {
  test("a parent picks what's happening, adds a note and alerts Pacifyco", async () => {
    const posted = renderHelp("parent");
    fireEvent.click(screen.getByRole("button", { name: /Emergency or report/ }));
    fireEvent.click(screen.getByLabelText("Something has been stolen"));
    fireEvent.change(screen.getByLabelText(/A few words/), { target: { value: "Bracelet missing" } });
    fireEvent.click(screen.getByRole("button", { name: "Yes, alert Pacifyco" }));
    await vi.waitFor(() =>
      expect(posted).toEqual([
        { url: expect.stringMatching(/\/parent\/bookings\/b1\/emergency$/), body: { kind: "theft", note: "Bracelet missing" } },
      ]),
    );
  });

  test("a sitter's choices", () => {
    renderHelp("sitter");
    fireEvent.click(screen.getByRole("button", { name: /Emergency or report/ }));
    expect(screen.getByLabelText("I'm being abused or I feel unsafe")).toBeTruthy();
    expect(screen.queryByLabelText("Something has been stolen")).toBeNull();
  });

  test("once raised, it says Pacifyco will call", () => {
    renderHelp("parent", true, { kind: "emergency", status: "open", created_at: "2030-01-01T00:00:00Z" });
    expect(screen.getByText(/Pacifyco has been alerted and will call you/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Emergency or report/ })).toBeNull();
  });

  test("nothing outside the booking", () => {
    renderHelp("parent", false);
    expect(screen.queryByRole("button", { name: /Emergency or report/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Report an issue" })).toBeNull();
  });
});

describe("Issues", () => {
  test("something else needs a note, then it's sent", async () => {
    const posted = renderHelp("sitter");
    fireEvent.click(screen.getByRole("button", { name: "Report an issue" }));
    expect(screen.getByText(/Only a man is at home/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Something else"));
    fireEvent.click(screen.getByRole("button", { name: "Send to Pacifyco" }));
    expect(screen.getByText("Please tell us what's wrong.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/What's happening\?/), { target: { value: "No key left out" } });
    fireEvent.click(screen.getByRole("button", { name: "Send to Pacifyco" }));
    await vi.waitFor(() =>
      expect(posted).toEqual([
        { url: expect.stringMatching(/\/sitter\/bookings\/b1\/issues$/), body: { topic: "other", note: "No key left out" } },
      ]),
    );
  });
});
