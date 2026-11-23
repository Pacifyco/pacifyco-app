import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../../lib/times";
import { jsonResponse } from "../../test/renderApp";
import {
  AdminComplaintPage,
  ComplaintsPage,
  HolidaysPage,
  nextTarget,
  timeLeft,
  type AdminComplaint,
  type AdminComplaintRow,
} from "./ComplaintsPages";

// Complaints, appeals and the Grievance Officer, for admins (CLAUDE.md 6.12; phase 10).

const HOUR = 3_600_000;
const inHours = (hours: number) => new Date(Date.now() + hours * HOUR).toISOString();

const ROW: AdminComplaintRow = {
  id: "c1",
  type: "booking",
  topic: "running_late",
  status: "open",
  person_name: "Priya Rao",
  person_role: "parent",
  created_at: kolkataTime("2030-01-07", 9),
  reply_by: inHours(5),
  resolve_by: inHours(29),
  first_reply_at: null,
  escalated_at: null,
  officer_acknowledged_at: null,
  late: true,
  serious: false,
  overdue: false,
};

const COMPLAINT: AdminComplaint = {
  ...ROW,
  description: "The sitter was an hour late.",
  happened_on: null,
  person: {
    id: "p1",
    full_name: "Priya Rao",
    role: "parent",
    email: "priya@example.com",
    phone: "+919876543210",
    status: "active",
  },
  booking_id: "b1",
  booking_starts_at: kolkataTime("2030-01-06", 9),
  resolution: null,
  resolved_at: null,
  appeal_outcome: null,
  decision: null,
  escalation_note: null,
  escalated_by_person: false,
  acknowledge_by: null,
  decide_by: null,
  officer_decision: null,
  officer_decided_at: null,
  messages: [],
  attachments: [{ id: "d1", type: "complaint_attachment", uploaded_at: kolkataTime("2030-01-07", 9) }],
  cannot_handle: null,
  is_officer: true,
};

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

const complaintPage = <Route path="/admin/complaints/:complaintId" element={<AdminComplaintPage />} />;
const posts = (calls: Call[]) => calls.filter((call) => call.method !== "GET");

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("The complaints queue", () => {
  test("each with who, what and the time left on its target", async () => {
    const late = { ...ROW, id: "c2", type: "payment", topic: null, overdue: true, reply_by: inHours(-3) };
    const calls = mockApi(() => [ROW, late]);
    renderAt("/admin/complaints", <Route path="/admin/complaints" element={<ComplaintsPage />} />);
    const first = await screen.findByRole("link", { name: /A booking: running late · Priya Rao \(parent\)/ });
    expect(first.getAttribute("href")).toBe("/admin/complaints/c1");
    expect(first.textContent).toContain("Waiting for a first reply · Raised Mon, 7 Jan · Late");
    expect(first.textContent).toContain("First reply: 5 h left");
    expect(screen.getByText("First reply: 3 h overdue").className).toContain("text-danger");

    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "appeals" } });
    await waitFor(() => expect(calls.at(-1)?.url).toMatch(/\/admin\/complaints\?view=appeals$/));
  });

  test("time left in words", () => {
    const now = new Date("2030-01-07T00:00:00Z");
    expect(timeLeft("2030-01-07T00:30:00Z", now)).toBe("30 min left");
    expect(timeLeft("2030-01-06T21:00:00Z", now)).toBe("3 h overdue");
    expect(timeLeft("2030-01-17T00:00:00Z", now)).toBe("10 days left");
    const escalated = { ...ROW, status: "escalated", escalated_at: "2030-01-06T12:00:00Z" };
    expect(nextTarget(escalated, now)).toBe("Acknowledge: 12 h left");
    const acknowledged = { ...escalated, officer_acknowledged_at: "2030-01-06T13:00:00Z" };
    expect(nextTarget(acknowledged, now)).toBe("Decide: 15 days left");
    expect(nextTarget({ ...ROW, first_reply_at: "x", type: "suspension" }, now)).toMatch(/^Decide: /);
    expect(nextTarget({ ...ROW, status: "resolved" }, now)).toBeNull();
  });
});

describe("One complaint", () => {
  test("reply, mark serious and resolve", async () => {
    const calls = mockApi(() => COMPLAINT);
    renderAt("/admin/complaints/c1", complaintPage);
    expect(await screen.findByRole("heading", { name: "A booking: running late" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Priya Rao" }).getAttribute("href")).toBe("/admin/parents/p1");
    const booking = screen.getByRole("link", { name: /The booking on Sun, 6 Jan/ });
    expect(booking.getAttribute("href")).toBe("/admin/bookings/b1");
    expect(screen.getByText(/Raised more than 24 hours after it happened/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "View file 1" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/Write to them/), { target: { value: "Sorry about that." } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Mark a serious safety matter" }));
    await waitFor(() => expect(posts(calls)).toHaveLength(2));
    fireEvent.click(screen.getByRole("button", { name: "Resolve the complaint" }));
    expect(screen.getByText("Please write something first.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/What was done/), { target: { value: "Spoke to the sitter." } });
    fireEvent.click(screen.getByRole("button", { name: "Resolve the complaint" }));
    await waitFor(() => expect(posts(calls)).toHaveLength(3));
    expect(posts(calls).map((call) => [call.url.replace(/^.*\/admin/, ""), call.body])).toEqual([
      ["/complaints/c1/messages", { body: "Sorry about that." }],
      ["/complaints/c1/serious", { serious: true }],
      ["/complaints/c1/resolve", { body: "Spoke to the sitter." }],
    ]);
  });

  test("the admin who made the decision can't handle the appeal", async () => {
    mockApi(() => ({
      ...COMPLAINT,
      type: "suspension",
      topic: null,
      booking_id: null,
      decision: {
        action: "suspended",
        kind: "safety",
        reason: "A report.",
        at: ROW.created_at,
        by: "Asha Admin",
        by_id: "a1",
      },
      cannot_handle: "You made the decision this appeal is against, so another admin must handle it.",
    }));
    renderAt("/admin/complaints/c1", complaintPage);
    expect(await screen.findByText(/another admin must handle it/)).toBeTruthy();
    expect(screen.getByText(/Suspended .* by Asha Admin · safety/)).toBeTruthy();
    expect(screen.queryByLabelText(/Write to them/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Decide the appeal" })).toBeNull();
  });

  test("deciding an appeal: upheld, and reinstated now", async () => {
    const calls = mockApi(() => ({
      ...COMPLAINT,
      type: "suspension",
      topic: null,
      decision: {
        action: "removed",
        kind: "strikes",
        reason: "Fifth strike.",
        at: ROW.created_at,
        by: null,
        by_id: null,
      },
    }));
    renderAt("/admin/complaints/c1", complaintPage);
    expect(await screen.findByText(/by the rules \(automatic\)/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/The reasons for the decision/), { target: { value: "A mistake." } });
    fireEvent.click(screen.getByRole("button", { name: "Decide the appeal" }));
    expect(screen.getByText("Choose upheld or rejected.")).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/Upheld/));
    fireEvent.click(screen.getByLabelText(/Reinstate the account now/));
    fireEvent.click(screen.getByRole("button", { name: "Decide the appeal" }));
    await waitFor(() =>
      expect(posts(calls)).toEqual([
        {
          url: expect.stringMatching(/\/admin\/complaints\/c1\/appeal$/),
          method: "POST",
          body: { outcome: "upheld", reinstate: true, note: "A mistake." },
        },
      ]),
    );
  });

  test("the Grievance Officer acknowledges and decides", async () => {
    const calls = mockApi(() => ({
      ...COMPLAINT,
      status: "escalated",
      escalated_at: kolkataTime("2030-01-09", 9),
      escalated_by_person: true,
      escalation_note: "Not sorted.",
      acknowledge_by: kolkataTime("2030-01-10", 9),
      decide_by: kolkataTime("2030-01-24", 9),
    }));
    renderAt("/admin/complaints/c1", complaintPage);
    expect(await screen.findByText("Not sorted.")).toBeTruthy();
    expect(screen.getByText(/They disagreed with how it was resolved/)).toBeTruthy();
    expect(screen.getByText(/Acknowledge by Thu, 10 Jan, 9:00 am · Decide by Thu, 24 Jan/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge it" }));
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    fireEvent.change(screen.getByLabelText(/Your written decision/), { target: { value: "Refunded, because…" } });
    fireEvent.click(screen.getByRole("button", { name: "Send the decision" }));
    await waitFor(() => expect(posts(calls)).toHaveLength(2));
    expect(posts(calls).map((call) => call.url.replace(/^.*\/admin/, ""))).toEqual([
      "/complaints/c1/acknowledge",
      "/complaints/c1/officer-decision",
    ]);
    expect(screen.queryByRole("button", { name: "Resolve the complaint" })).toBeNull();
  });
});

describe("Public holidays", () => {
  test("added and removed", async () => {
    const calls = mockApi(() => [{ day: "2031-01-26", name: "Republic Day" }]);
    renderAt("/admin/holidays", <Route path="/admin/holidays" element={<HolidaysPage />} />);
    expect(await screen.findByText(/Sun, 26 Jan 2031 · Republic Day/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add the holiday" }));
    expect(screen.getByText("Choose the day and give it a name.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Day"), { target: { value: "2031-08-15" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Independence Day" } });
    fireEvent.click(screen.getByRole("button", { name: "Add the holiday" }));
    await waitFor(() => expect(posts(calls)).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Remove Republic Day" }));
    await waitFor(() => expect(posts(calls)).toHaveLength(2));
    expect(posts(calls).map((call) => [call.method, call.url.replace(/^.*\/admin/, ""), call.body])).toEqual([
      ["POST", "/holidays", { day: "2031-08-15", name: "Independence Day" }],
      ["DELETE", "/holidays/2031-01-26", null],
    ]);
  });
});
