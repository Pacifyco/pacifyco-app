import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../../lib/times";
import { jsonResponse } from "../../test/renderApp";
import { AccountSection, type AdminAccount } from "./AccountSection";

// Suspend, remove or reinstate (phase 10): a kind of reason and the reason, which the person is emailed;
// upcoming bookings are cancelled; a low-ratings decision waits for her response (6.11).

const ACTIVE: AdminAccount = {
  id: "s1",
  role: "sitter",
  status: "active",
  upcoming_bookings: 2,
  under_way_bookings: 0,
  ratings_wait: null,
  five_strikes: false,
  history: [],
};

const SUSPENDED: AdminAccount = {
  ...ACTIVE,
  status: "suspended",
  upcoming_bookings: 0,
  history: [
    { action: "suspended", kind: "safety", reason: "A theft report.", by: "Asha Admin", at: kolkataTime("2030-01-05", 10) },
  ],
};

function renderWith(data: AdminAccount, after?: AdminAccount) {
  const posted: { url: string; body: unknown }[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: JSON.parse(init.body as string) });
      return Promise.resolve(jsonResponse(after ?? data));
    }
    return Promise.resolve(jsonResponse(data));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AccountSection profileId="s1" />
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("An account, for admins", () => {
  test("suspending needs a kind and a reason, and says what it cancels", async () => {
    const posted = renderWith(ACTIVE, SUSPENDED);
    expect(await screen.findByText("Active.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reinstate" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Suspend" }));
    expect(screen.getByText(/This cancels 2 upcoming bookings and refunds any/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Suspend the account" }));
    expect(screen.getByText("Choose the kind of reason.")).toBeTruthy();
    expect(screen.getByText("Please give a reason. The person will see it.")).toBeTruthy();
    expect(posted).toEqual([]);

    fireEvent.change(screen.getByLabelText(/Kind of reason/), { target: { value: "safety" } });
    fireEvent.change(screen.getByLabelText(/The reason/), { target: { value: "A theft report." } });
    fireEvent.click(screen.getByRole("button", { name: "Suspend the account" }));
    expect(await screen.findByText("Suspended.")).toBeTruthy();
    expect(screen.getByText(/Suspended · Safety or conduct · Sat, 5 Jan, 10:00 am/)).toBeTruthy();
    expect(screen.getByText("By Asha Admin")).toBeTruthy();
    expect(posted).toEqual([
      { url: expect.stringMatching(/\/admin\/accounts\/s1\/suspend$/), body: { kind: "safety", reason: "A theft report." } },
    ]);
  });

  test("a low-ratings decision shows why it must wait", async () => {
    renderWith({ ...ACTIVE, ratings_wait: "She has 12 hours from being told to respond." });
    fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
    expect(screen.queryByText(/She has 12 hours/)).toBeNull();
    fireEvent.change(screen.getByLabelText(/Kind of reason/), { target: { value: "low_ratings" } });
    expect(screen.getByText("She has 12 hours from being told to respond.")).toBeTruthy();
  });

  test("a parent has no ratings or strikes kinds", async () => {
    renderWith({ ...ACTIVE, role: "parent" });
    fireEvent.click(await screen.findByRole("button", { name: "Suspend" }));
    const options = Array.from(screen.getByLabelText(/Kind of reason/).querySelectorAll("option")).map((o) => o.textContent);
    expect(options).toEqual(["Choose…", "Safety or conduct", "Other"]);
  });

  test("reinstating, with a reason", async () => {
    const posted = renderWith(SUSPENDED, { ...ACTIVE, upcoming_bookings: 0 });
    expect(screen.queryByRole("button", { name: "Suspend" })).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "Reinstate" }));
    fireEvent.change(screen.getByLabelText(/Why reinstate\?/), { target: { value: "It wasn't her." } });
    fireEvent.click(screen.getByRole("button", { name: "Reinstate" }));
    expect(await screen.findByText("Active.")).toBeTruthy();
    expect(posted).toEqual([
      { url: expect.stringMatching(/\/admin\/accounts\/s1\/reinstate$/), body: { reason: "It wasn't her." } },
    ]);
  });

  test("5 strikes must come down first; the rules' own decisions say so", async () => {
    renderWith({
      ...ACTIVE,
      status: "removed",
      five_strikes: true,
      history: [{ action: "removed", kind: "strikes", reason: "Five strikes in 6 months.", by: null, at: kolkataTime("2030-01-05", 10) }],
    });
    expect(await screen.findByText(/She has 5 strikes counting/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reinstate" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove" })).toBeNull();
    expect(screen.getByText("By the rules")).toBeTruthy();
  });

  test("bookings under way are left for a call", async () => {
    renderWith({ ...ACTIVE, under_way_bookings: 1 });
    expect(await screen.findByText(/1 booking is under way\. Suspending or removing doesn't cancel it/)).toBeTruthy();
  });
});
