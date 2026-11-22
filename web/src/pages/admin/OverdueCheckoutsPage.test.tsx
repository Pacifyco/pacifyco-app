import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../../test/renderApp";
import { OverdueCheckoutsPage, type NeedsAttentionItem } from "./OverdueCheckoutsPage";

// Overdue check-outs and locked codes (CLAUDE.md 6.7): call both people, then close it by hand.

const minutesFromNow = (minutes: number) => new Date(Date.now() + minutes * 60_000).toISOString();

const OVERDUE: NeedsAttentionItem = {
  booking_id: "b1",
  overdue: true,
  starts_at: minutesFromNow(-150),
  ends_at: minutesFromNow(-35),
  parent_name: "Priya Rao",
  parent_phone: "+919876543210",
  sitter_name: "Lakshmi Nair",
  sitter_phone: "+919812345678",
  checked_in: true,
};

function renderWith(list: NeedsAttentionItem[]) {
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
        <OverdueCheckoutsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Overdue check-outs", () => {
  test("what happened and both phone numbers", async () => {
    renderWith([OVERDUE]);
    expect(await screen.findByText("Check-out overdue")).toBeTruthy();
    expect(screen.getByText("Still checked in more than 30 minutes past the end.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "+91 98765 43210" }).getAttribute("href")).toBe("tel:+919876543210");
    expect(screen.getByRole("link", { name: "+91 98123 45678" })).toBeTruthy();
  });

  test("a locked booking reads differently", async () => {
    renderWith([{ ...OVERDUE, overdue: false }]);
    expect(await screen.findByText("Codes locked")).toBeTruthy();
    expect(screen.getByText("Too many wrong codes were entered; code entry is locked.")).toBeTruthy();
  });

  test("closing needs a reason", async () => {
    const posted = renderWith([OVERDUE]);
    fireEvent.click(await screen.findByRole("button", { name: "Close the booking" }));
    fireEvent.click(screen.getByRole("button", { name: "Close the booking" }));
    expect(screen.getByText("Please say why you're closing it.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Why are you closing it\?/), {
      target: { value: "Called both; she forgot to check out." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Close the booking" }));
    await vi.waitFor(() =>
      expect(posted).toEqual([
        {
          url: expect.stringMatching(/\/admin\/bookings\/b1\/close$/),
          body: { reason: "Called both; she forgot to check out.", overtime_hours: null, pay_hours: null },
        },
      ]),
    );
  });

  test("the admin may choose to charge overtime", async () => {
    const posted = renderWith([OVERDUE]);
    fireEvent.click(await screen.findByRole("button", { name: "Close the booking" }));
    expect((screen.getByLabelText(/Charge overtime\?/) as HTMLSelectElement).value).toBe("0"); // none by default
    fireEvent.change(screen.getByLabelText(/Why are you closing it\?/), { target: { value: "Parent back 2 hours late" } });
    fireEvent.change(screen.getByLabelText(/Charge overtime\?/), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Close the booking" }));
    await vi.waitFor(() =>
      expect(posted).toEqual([
        {
          url: expect.stringMatching(/\/admin\/bookings\/b1\/close$/),
          body: { reason: "Parent back 2 hours late", overtime_hours: 2, pay_hours: null },
        },
      ]),
    );
  });

  test("none", async () => {
    renderWith([]);
    expect(await screen.findByText("Nothing needs attention.")).toBeTruthy();
  });

  test("she never checked in: the admin may choose hours to pay her, nothing by default", async () => {
    const posted = renderWith([{ ...OVERDUE, overdue: false, checked_in: false }]);
    fireEvent.click(await screen.findByRole("button", { name: "Close the booking" }));
    const pay = screen.getByLabelText(/Pay the sitter\?/) as HTMLSelectElement;
    expect(pay.value).toBe("0");
    fireEvent.change(screen.getByLabelText(/Why are you closing it\?/), { target: { value: "Codes locked at the door" } });
    fireEvent.change(pay, { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Close the booking" }));
    await vi.waitFor(() => expect(posted[0]?.body).toEqual({ reason: "Codes locked at the door", overtime_hours: null, pay_hours: 1 }));
  });

  test("she checked in: no pay choice (she's paid for the hours she worked)", async () => {
    renderWith([OVERDUE]);
    fireEvent.click(await screen.findByRole("button", { name: "Close the booking" }));
    expect(screen.queryByLabelText(/Pay the sitter\?/)).toBeNull();
  });
});
