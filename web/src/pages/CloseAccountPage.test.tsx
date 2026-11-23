import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { AccountClosed } from "../auth/RequireRole";
import { jsonResponse } from "../test/renderApp";
import { CloseAccountPage, type Closing } from "./CloseAccountPage";
import { NewComplaintPage } from "./HelpPages";

// Closing their own account, and data requests (CLAUDE.md 6.13; phase 10).

type Call = { url: string; method: string; body: unknown };

function mockApi(answer: (url: string, method: string) => unknown) {
  const calls: Call[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: typeof init?.body === "string" ? JSON.parse(init.body) : null });
    return Promise.resolve(jsonResponse(answer(url, method)));
  }) as unknown as typeof fetch);
  return calls;
}

function renderAt(path: string, routes: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>{routes}</Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const OPEN: Closing = { can_close: true, reasons: [], owed_paise: 0, pay_due_paise: 0 };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Closing their account", () => {
  test("ticked, then closed, with an optional reason", async () => {
    const calls = mockApi((_, method) => (method === "POST" ? { status: "closed" } : OPEN));
    renderAt(
      "/parent/close-account",
      <Route path="/parent/close-account" element={<CloseAccountPage role="parent" />} />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Close my account" }));
    expect(screen.getByText("Please tick the box first.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Why are you leaving/), { target: { value: "Moving away." } });
    fireEvent.click(screen.getByLabelText(/I understand I won't be able to use this account/));
    fireEvent.click(screen.getByRole("button", { name: "Close my account" }));
    await waitFor(() =>
      expect(calls.filter((call) => call.method === "POST")).toEqual([
        { url: expect.stringMatching(/\/me\/close$/), method: "POST", body: { reason: "Moving away." } },
      ]),
    );
    expect(screen.getByRole("link", { name: "ask us from Help" }).getAttribute("href")).toBe(
      "/parent/help/new?data=deletion",
    );
  });

  test("a sitter is told her pay still comes", async () => {
    mockApi(() => ({ ...OPEN, pay_due_paise: 60_000 }));
    renderAt(
      "/sitter/close-account",
      <Route path="/sitter/close-account" element={<CloseAccountPage role="sitter" />} />,
    );
    expect(await screen.findByText(/The ₹600 you've earned and haven't been paid yet/)).toBeTruthy();
    expect(screen.getByText(/families won't see you/)).toBeTruthy();
  });

  test("not yet: what's in the way", async () => {
    mockApi(() => ({
      can_close: false,
      reasons: ["You owe a payment to Pacifyco. Please pay it first."],
      owed_paise: 69_900,
      pay_due_paise: 0,
    }));
    renderAt(
      "/parent/close-account",
      <Route path="/parent/close-account" element={<CloseAccountPage role="parent" />} />,
    );
    expect(await screen.findByText("You owe a payment to Pacifyco. Please pay it first.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Pay the ₹699 you owe" }).getAttribute("href")).toBe("/parent/payments");
    expect(screen.queryByRole("button", { name: "Close my account" })).toBeNull();
  });

  test("once closed, how to reopen it", () => {
    render(<AccountClosed />);
    expect(screen.getByRole("heading", { name: "You've closed this account." })).toBeTruthy();
    expect(screen.getByRole("link", { name: "founders@pacifyco.in" })).toBeTruthy();
  });
});

describe("Data requests", () => {
  test("from the close page, a deletion request is ready to send", async () => {
    const calls = mockApi(() => ({ id: "c1" }));
    renderAt(
      "/parent/help/new?data=deletion",
      <>
        <Route path="/parent/help/new" element={<NewComplaintPage role="parent" />} />
        <Route path="/parent/help/:complaintId" element={<p>Opened</p>} />
      </>,
    );
    expect((screen.getByLabelText("What's it about?") as HTMLSelectElement).value).toBe("data_request");
    expect((screen.getByLabelText("What would you like?") as HTMLSelectElement).value).toBe("deletion");
    expect(screen.queryByLabelText(/When did it happen/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Tell us more"), { target: { value: "Please delete everything." } });
    fireEvent.click(screen.getByRole("button", { name: "Send my complaint" }));
    expect(await screen.findByText("Opened")).toBeTruthy();
    expect(calls[0].body).toEqual({
      type: "data_request",
      description: "Please delete everything.",
      booking_id: null,
      happened_on: null,
      request_kind: "deletion",
    });
  });

  test("what they'd like must be chosen", () => {
    const calls = mockApi(() => ({}));
    renderAt("/sitter/help/new", <Route path="/sitter/help/new" element={<NewComplaintPage role="sitter" />} />);
    fireEvent.change(screen.getByLabelText("What's it about?"), { target: { value: "data_request" } });
    fireEvent.change(screen.getByLabelText("Tell us more"), { target: { value: "A copy, please." } });
    fireEvent.click(screen.getByRole("button", { name: "Send my complaint" }));
    expect(screen.getByText("Please choose what you'd like.")).toBeTruthy();
    expect(calls).toEqual([]);
  });
});
