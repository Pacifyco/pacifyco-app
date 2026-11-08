import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../../test/renderApp";
import { FamilyReviewPage } from "./FamilyReviewPage";
import { SitterReviewPage } from "./SitterReviewPage";
import { VerificationQueuePage } from "./VerificationQueuePage";

type Call = { method: string; path: string; body: unknown };
type Handler = (body: unknown) => Response;

function mockApi(routes: Record<string, Handler>) {
  const calls: Call[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const method = init?.method ?? "GET";
    const body = init?.body ? (JSON.parse(init.body as string) as unknown) : null;
    calls.push({ method, path, body });
    const handler = routes[`${method} ${path}`];
    return handler ? Promise.resolve(handler(body)) : Promise.reject(new Error(`unexpected ${method} ${path}`));
  }) as typeof fetch);
  return calls;
}

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/admin/verifications" element={<VerificationQueuePage />} />
          <Route path="/admin/sitters/:sitterId" element={<SitterReviewPage />} />
          <Route path="/admin/parents/:parentId" element={<FamilyReviewPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const SITTER = {
  id: "s1",
  full_name: "Lakshmi Nair",
  email: "lakshmi@example.com",
  phone: "+919876543210",
  pin_code: "560034",
  profile_status: "pending",
  signed_up_at: "2026-11-01T10:00:00Z",
  date_of_birth: "1998-04-02",
  bio: "I love storytime.",
  years_experience: 4,
  age_groups: ["2-5"],
  languages: ["English", "Kannada"],
  first_aid: true,
  has_health_disclosure: true,
  payout_method: "upi",
  onboarding_status: "in_progress",
  level: null,
  steps: {
    profile: "approved",
    identity_documents: "pending",
    police_certificate: "pending",
    references: "pending",
    psych_test: "pending",
  },
  documents: [{ id: "d1", type: "police_certificate", uploaded_at: "2026-11-02T10:00:00Z" }],
  references: [
    { id: "r1", name: "Asha Rao", phone: "+919876500000", relationship: "Former employer", outcome: "pending", notes: null },
  ],
  psych_attempt: { id: "a1", status: "submitted", submitted_at: "2026-11-03T10:00:00Z" },
};

const PSYCH = {
  status: "submitted",
  notes: null,
  answers: [{ question_id: "q1", kind: "short_answer", prompt: "A child won't nap. What do you do?", options: null, answer_text: "Read quietly together." }],
};

const sitterRoutes = (overrides: Record<string, Handler> = {}): Record<string, Handler> => ({
  "GET /admin/sitters/s1": () => jsonResponse(SITTER),
  "GET /admin/psych-attempts/a1": () => jsonResponse(PSYCH),
  "GET /admin/verifications": () => jsonResponse({ sitters: [], families: [] }),
  ...overrides,
});

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("the verification queue", () => {
  test("lists sitters and families, each linking to its review", async () => {
    mockApi({
      "GET /admin/verifications": () =>
        jsonResponse({
          sitters: [{ ...SITTER, steps_approved: 1, steps_total: 5, level: null }],
          families: [{ id: "p1", full_name: "Priya Rao", email: "priya@example.com", signed_up_at: "2026-11-01T10:00:00Z", children_to_review: 2 }],
        }),
    });
    renderAt("/admin/verifications");

    expect((await screen.findByRole("link", { name: /Lakshmi Nair/ })).getAttribute("href")).toBe("/admin/sitters/s1");
    expect(screen.getByText("1 of 5 steps")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Priya Rao/ }).getAttribute("href")).toBe("/admin/parents/p1");
    expect(screen.getByText("2 children to check")).toBeTruthy();
  });

  test("says so when nothing is waiting", async () => {
    mockApi({ "GET /admin/verifications": () => jsonResponse({ sitters: [], families: [] }) });
    renderAt("/admin/verifications");
    expect(await screen.findByText("No sitters are waiting. Nice work.")).toBeTruthy();
    expect(screen.getByText("No birth certificates are waiting.")).toBeTruthy();
  });
});

describe("reviewing a sitter", () => {
  test("shows her steps, profile and psychology answers, but not her health details", async () => {
    mockApi(sitterRoutes());
    renderAt("/admin/sitters/s1");

    expect(await screen.findByRole("heading", { name: "Lakshmi Nair" })).toBeTruthy();
    expect(screen.getByText("1 of 5 approved")).toBeTruthy();
    expect(screen.getByText("English, Kannada")).toBeTruthy();
    expect(await screen.findByText("Read quietly together.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show health disclosure" })).toBeTruthy();
  });

  test("approving a step posts the decision with its notes", async () => {
    const calls = mockApi(
      sitterRoutes({ "POST /admin/sitters/s1/steps/police_certificate": () => jsonResponse({ status: "approved" }) }),
    );
    renderAt("/admin/sitters/s1");

    const notes = await screen.findByLabelText(/Notes on the police certificate/);
    fireEvent.change(notes, { target: { value: "Checked with the station" } });
    const section = notes.closest("section")!;
    fireEvent.click(Array.from(section.querySelectorAll("button")).find((b) => b.textContent === "Approve")!);

    await waitFor(() =>
      expect(calls).toContainEqual({
        method: "POST",
        path: "/admin/sitters/s1/steps/police_certificate",
        body: { approved: true, notes: "Checked with the station" },
      }),
    );
  });

  test("passing the psychology test sends passed: true", async () => {
    const calls = mockApi(sitterRoutes({ "POST /admin/psych-attempts/a1/decision": () => jsonResponse({ id: "a1", status: "passed" }) }));
    renderAt("/admin/sitters/s1");

    fireEvent.click(await screen.findByRole("button", { name: "Pass" }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "POST", path: "/admin/psych-attempts/a1/decision", body: { passed: true, notes: null } }),
    );
  });

  test("opening the health disclosure fetches it from its logged endpoint", async () => {
    const calls = mockApi(
      sitterRoutes({ "GET /admin/sitters/s1/health-disclosure": () => jsonResponse({ disclosure: "Mild asthma" }) }),
    );
    renderAt("/admin/sitters/s1");

    fireEvent.click(await screen.findByRole("button", { name: "Show health disclosure" }));
    expect(await screen.findByText("Mild asthma")).toBeTruthy();
    expect(calls.filter((call) => call.path === "/admin/sitters/s1/health-disclosure")).toHaveLength(1);
  });

  test("setting her level", async () => {
    const calls = mockApi(sitterRoutes({ "PUT /admin/sitters/s1/level": () => jsonResponse({ level: "unwind" }) }));
    renderAt("/admin/sitters/s1");

    fireEvent.change(await screen.findByLabelText("Level"), { target: { value: "unwind" } });
    fireEvent.click(screen.getByRole("button", { name: "Save level" }));
    await waitFor(() => expect(calls).toContainEqual({ method: "PUT", path: "/admin/sitters/s1/level", body: { level: "unwind" } }));
  });

  test("approval shows the API's reason when steps are still waiting", async () => {
    mockApi(
      sitterRoutes({
        "POST /admin/sitters/s1/decision": () =>
          jsonResponse(
            { error: { code: "steps_not_approved", message: "Every onboarding step must be approved first", details: null } },
            409,
          ),
      }),
    );
    renderAt("/admin/sitters/s1");

    fireEvent.click(await screen.findByRole("button", { name: "Approve and go live" }));
    expect(await screen.findByText("Every onboarding step must be approved first")).toBeTruthy();
  });

  test("viewing a document opens its signed link in a new tab", async () => {
    const tab = { opener: {}, location: { href: "" }, close: vi.fn() };
    const open = vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
    mockApi(sitterRoutes({ "GET /admin/documents/d1/view-url": () => jsonResponse({ url: "https://storage.example/d1?token=x" }) }));
    renderAt("/admin/sitters/s1");

    fireEvent.click(await screen.findByRole("button", { name: "View police clearance certificate" }));
    await waitFor(() => expect(tab.location.href).toBe("https://storage.example/d1?token=x"));
    expect(tab.opener).toBeNull();
    open.mockRestore();
  });
});

describe("reviewing a family", () => {
  const FAMILY = {
    id: "p1",
    full_name: "Priya Rao",
    email: "priya@example.com",
    phone: null,
    pin_code: "560034",
    verification_status: "pending",
    signed_up_at: "2026-11-01T10:00:00Z",
    children: [
      {
        id: "c1",
        name: "Asha",
        date_of_birth: "2023-01-01",
        verification_status: "pending",
        verified_at: null,
        verification_notes: null,
        birth_certificates: [{ id: "d9", type: "birth_certificate", uploaded_at: "2026-11-02T10:00:00Z" }],
      },
      {
        id: "c2",
        name: "Kabir",
        date_of_birth: "2021-06-01",
        verification_status: "approved",
        verified_at: "2026-11-03T10:00:00Z",
        verification_notes: null,
        birth_certificates: [],
      },
    ],
  };

  test("approving a child posts the decision; verified children show the certificate is gone", async () => {
    const calls = mockApi({
      "GET /admin/parents/p1": () => jsonResponse(FAMILY),
      "GET /admin/verifications": () => jsonResponse({ sitters: [], families: [] }),
      "POST /admin/children/c1/decision": () => jsonResponse({ status: "approved" }),
    });
    renderAt("/admin/parents/p1");

    expect(await screen.findByRole("heading", { name: "Priya Rao" })).toBeTruthy();
    expect(screen.getByText(/The birth certificate has been deleted/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "View birth certificate" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "POST", path: "/admin/children/c1/decision", body: { approved: true, notes: null } }),
    );
  });
});
