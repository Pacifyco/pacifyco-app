import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import { AppealSection, ComplaintPage, HelpPage, NewComplaintPage, type Complaint } from "./HelpPages";

// Help and complaints for parents and sitters (CLAUDE.md 6.12; phase 10).

const COMPLAINT: Complaint = {
  id: "c1",
  type: "payment",
  status: "replied",
  description: "I was charged twice.",
  created_at: kolkataTime("2030-01-07", 9),
  request_kind: null,
  booking_id: null,
  happened_on: null,
  late: false,
  reply_by: kolkataTime("2030-01-08", 9),
  resolve_by: kolkataTime("2030-01-09", 9),
  first_reply_at: kolkataTime("2030-01-07", 10),
  resolved_at: null,
  resolution: null,
  appeal_outcome: null,
  escalated_at: null,
  officer_acknowledged_at: null,
  officer_decision: null,
  officer_decided_at: null,
  can_write: true,
  can_escalate: false,
  can_attach: true,
  messages: [
    { id: "m1", from_pacifyco: true, body: "We're looking into it.", at: kolkataTime("2030-01-07", 10) },
    { id: "m2", from_pacifyco: false, body: "Thank you.", at: kolkataTime("2030-01-07", 11) },
  ],
  attachments: [],
};

type Call = { url: string; method: string; body: unknown };

function mockApi(answer: (url: string, method: string) => unknown) {
  const calls: Call[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : (init?.body ?? null);
    calls.push({ url, method, body });
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

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Help", () => {
  test("their complaints, and a way to raise one", async () => {
    mockApi(() => [COMPLAINT]);
    renderAt("/parent/help", <Route path="/parent/help" element={<HelpPage role="parent" />} />);
    const link = await screen.findByRole("link", { name: /A payment · Mon, 7 Jan/ });
    expect(link.getAttribute("href")).toBe("/parent/help/c1");
    expect(link.textContent).toContain("We've replied");
    expect(screen.getByRole("link", { name: "Raise a complaint" }).getAttribute("href")).toBe("/parent/help/new");
    expect(screen.getByText(/We'll reply within 24 hours/)).toBeTruthy();
  });

  test("raising one: what it's about and what happened are needed", async () => {
    const calls = mockApi((url) => (url.endsWith("/me/complaints") ? COMPLAINT : COMPLAINT));
    renderAt(
      "/sitter/help/new",
      <>
        <Route path="/sitter/help/new" element={<NewComplaintPage role="sitter" />} />
        <Route path="/sitter/help/:complaintId" element={<p>Opened</p>} />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Send my complaint" }));
    expect(screen.getByText("Please choose what it's about.")).toBeTruthy();
    expect(screen.getByText("Please tell us what happened.")).toBeTruthy();
    expect(screen.getByRole("option", { name: "A family" })).toBeTruthy(); // sitters complain about a family
    expect(calls).toEqual([]);

    fireEvent.change(screen.getByLabelText("What's it about?"), { target: { value: "payment" } });
    fireEvent.change(screen.getByLabelText(/When did it happen/), { target: { value: "2030-01-06" } });
    fireEvent.change(screen.getByLabelText("What happened?"), { target: { value: "  Paid late.  " } });
    fireEvent.click(screen.getByRole("button", { name: "Send my complaint" }));
    expect(await screen.findByText("Opened")).toBeTruthy();
    expect(calls[0]).toEqual({
      url: expect.stringMatching(/\/me\/complaints$/),
      method: "POST",
      body: {
        type: "payment",
        description: "Paid late.",
        booking_id: null,
        happened_on: "2030-01-06",
        request_kind: null,
      },
    });
  });

  test("from a booking, it's about that booking, with a file", async () => {
    const calls = mockApi((url) => {
      if (url.endsWith("/documents/upload-url")) return { document_id: "d1", upload_url: "https://storage/put" };
      if (url.endsWith("/confirm")) return { status: "uploaded" };
      return COMPLAINT;
    });
    renderAt(
      "/parent/help/new?booking=b1",
      <>
        <Route path="/parent/help/new" element={<NewComplaintPage role="parent" />} />
        <Route path="/parent/help/:complaintId" element={<p>Opened</p>} />
      </>,
    );
    expect(screen.queryByLabelText("What's it about?")).toBeNull();
    fireEvent.change(screen.getByLabelText("What happened?"), { target: { value: "She was rude." } });
    const file = new File(["%PDF"], "note.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/Files/), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Send my complaint" }));
    expect(await screen.findByText("Opened")).toBeTruthy();
    expect(calls.map((call) => [call.method, call.url.replace(/^.*\/\/[^/]+/, "")])).toEqual([
      ["POST", "/me/complaints"],
      ["POST", "/documents/upload-url"],
      ["PUT", "/put"],
      ["POST", "/documents/d1/confirm"],
    ]);
    expect(calls[0].body).toMatchObject({ type: "booking", booking_id: "b1", happened_on: null });
    expect(calls[1].body).toEqual({ type: "complaint_attachment", complaint_id: "c1" });
  });

  test("too many or the wrong files are refused before sending", async () => {
    const calls = mockApi(() => COMPLAINT);
    renderAt("/parent/help/new", <Route path="/parent/help/new" element={<NewComplaintPage role="parent" />} />);
    fireEvent.change(screen.getByLabelText("What's it about?"), { target: { value: "other" } });
    fireEvent.change(screen.getByLabelText("What happened?"), { target: { value: "Something" } });
    const zip = new File(["x"], "a.zip", { type: "application/zip" });
    fireEvent.change(screen.getByLabelText(/Files/), { target: { files: [zip] } });
    fireEvent.click(screen.getByRole("button", { name: "Send my complaint" }));
    expect(screen.getByText("Please choose a PDF, JPG or PNG file.")).toBeTruthy();
    const pdf = new File(["%PDF"], "a.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/Files/), { target: { files: [pdf, pdf, pdf, pdf] } });
    fireEvent.click(screen.getByRole("button", { name: "Send my complaint" }));
    expect(screen.getByText("Please choose up to 3 files.")).toBeTruthy();
    expect(calls).toEqual([]);
  });
});

describe("A complaint", () => {
  test("the conversation, and writing back", async () => {
    const calls = mockApi(() => COMPLAINT);
    renderAt("/parent/help/c1", <Route path="/parent/help/:complaintId" element={<ComplaintPage role="parent" />} />);
    expect(await screen.findByRole("heading", { name: "A payment" })).toBeTruthy();
    expect(screen.getByText(/We've replied · Raised Mon, 7 Jan/)).toBeTruthy();
    expect(screen.getByText(/We aim to sort it out by Wed, 9 Jan, 9:00 am/)).toBeTruthy();
    const messages = screen.getByRole("list", { name: "Messages" });
    expect(messages.textContent).toContain("Pacifyco · Mon, 7 Jan, 10:00 am");
    expect(messages.textContent).toContain("You · Mon, 7 Jan, 11:00 am");
    expect(screen.queryByRole("button", { name: /Grievance Officer/ })).toBeNull();

    fireEvent.change(screen.getByLabelText("Write to us"), { target: { value: "Any news?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() =>
      expect(calls.find((call) => call.method === "POST")).toEqual({
        url: expect.stringMatching(/\/me\/complaints\/c1\/messages$/),
        method: "POST",
        body: { body: "Any news?" },
      }),
    );
  });

  test("resolved: they can disagree and send it to the Grievance Officer", async () => {
    const resolved = { ...COMPLAINT, status: "resolved", resolution: "Refunded.", can_escalate: true };
    const calls = mockApi(() => resolved);
    renderAt("/sitter/help/c1", <Route path="/sitter/help/:complaintId" element={<ComplaintPage role="sitter" />} />);
    expect(await screen.findByText("Refunded.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "I disagree: send it to the Grievance Officer" }));
    fireEvent.click(screen.getByRole("button", { name: "Send to the Grievance Officer" }));
    expect(screen.getByText("Please tell us why you disagree.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Why do you disagree/), { target: { value: "Not refunded." } });
    fireEvent.click(screen.getByRole("button", { name: "Send to the Grievance Officer" }));
    await waitFor(() =>
      expect(calls.find((call) => call.method === "POST")).toEqual({
        url: expect.stringMatching(/\/me\/complaints\/c1\/escalate$/),
        method: "POST",
        body: { body: "Not refunded." },
      }),
    );
  });

  test("the Grievance Officer's decision", async () => {
    mockApi(() => ({
      ...COMPLAINT,
      status: "closed",
      officer_decision: "Refunded in full, because…",
      officer_decided_at: kolkataTime("2030-01-10", 9),
      can_write: false,
    }));
    renderAt("/parent/help/c1", <Route path="/parent/help/:complaintId" element={<ComplaintPage role="parent" />} />);
    expect(await screen.findByText("Refunded in full, because…")).toBeTruthy();
    expect(screen.getByText(/Our Grievance Officer's decision, Thu, 10 Jan/)).toBeTruthy();
    expect(screen.queryByLabelText("Write to us")).toBeNull();
  });
});

describe("Appealing a decision on the account", () => {
  const DECISION = { action: "suspended", reason: "Rude to a sitter.", at: kolkataTime("2030-01-07", 9) };

  test("the reason, and an appeal within 15 days", async () => {
    const calls = mockApi((_, method) =>
      method === "POST"
        ? {
            decision: DECISION,
            appeal_by: null,
            can_appeal: false,
            appeal: { ...COMPLAINT, type: "suspension", status: "open", messages: [] },
          }
        : { decision: DECISION, appeal_by: kolkataTime("2030-01-22", 9), can_appeal: true, appeal: null },
    );
    renderAt("/parent", <Route path="/parent" element={<AppealSection />} />);
    expect(await screen.findByText("Rude to a sitter.")).toBeTruthy();
    expect(screen.getByText(/Paused on Mon, 7 Jan/)).toBeTruthy();
    expect(screen.getByText(/You can appeal until Tue, 22 Jan/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Send my appeal" }));
    expect(screen.getByText("Please tell us why we should look at it again.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Appeal this decision/), { target: { value: "It wasn't me." } });
    fireEvent.click(screen.getByRole("button", { name: "Send my appeal" }));
    expect(await screen.findByText(/An admin who wasn't part of the decision will look at it/)).toBeTruthy();
    expect(calls.at(-1)).toEqual({
      url: expect.stringMatching(/\/me\/appeal$/),
      method: "POST",
      body: { body: "It wasn't me." },
    });
  });

  test("too late, or nothing to appeal", async () => {
    mockApi(() => ({ decision: DECISION, appeal_by: kolkataTime("2030-01-22", 9), can_appeal: false, appeal: null }));
    renderAt("/parent", <Route path="/parent" element={<AppealSection />} />);
    expect(await screen.findByText("The 15 days to appeal this decision have passed.")).toBeTruthy();
  });
});
