import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { AuthProvider } from "../auth/AuthProvider";
import { jsonResponse } from "../test/renderApp";
import { SitterApplicationPage } from "./SitterApplicationPage";

// Needs no sign-in session to render, same as FamilyPage: apiFetch sends no Authorization header
// when there isn't one, and every test here stubs fetch by URL directly. Wrapped in a MemoryRouter
// because the last step navigates to the psychology screening page.
function renderPage(path = "/sitter/application") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter initialEntries={[path]}>
          <SitterApplicationPage />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

type Call = { url: string; init?: RequestInit };

const FILLED_PROFILE = {
  date_of_birth: "1995-06-15",
  bio: "I love storytime.",
  years_experience: 5,
  age_groups: ["Toddler"],
  languages: ["English"],
  first_aid: false,
  reference_shared_consent: false,
  onboarding_status: "in_progress",
};

/** Everything before References is done, so References and Payment details can be opened. */
const UP_TO_REFERENCES = { profile: FILLED_PROFILE, healthSaved: true };

function mockApi(overrides: Record<string, unknown> = {}) {
  const calls: Call[] = [];
  const state = {
    profile: {
      date_of_birth: null as string | null,
      bio: null as string | null,
      years_experience: null as number | null,
      age_groups: [] as string[],
      languages: [] as string[],
      first_aid: false,
      reference_shared_consent: false,
      onboarding_status: "in_progress",
    },
    "health-disclosure": { disclosure: null as string | null },
    healthSaved: false,
    "payout-details": {
      method: null as string | null,
      account_holder_name: null as string | null,
      account_number: null as string | null,
      ifsc_code: null as string | null,
      upi_id: null as string | null,
    },
    references: [] as unknown[],
    // Uploaded so far (the upload itself is tested in DocumentUpload.test.tsx).
    documents: ["photo", "government_id", "college_or_work_id"] as string[],
    ...overrides,
  };
  // Her eight steps, worked out from what's saved, like the API (app/services/checklists.py).
  function checklist() {
    const p = state.profile;
    const has = (type: string) => state.documents.includes(type);
    const status = (done: boolean, finished = "waiting") => (done ? finished : "to_do");
    const items = [
      { key: "consent", status: "done" },
      { key: "details", status: "done" },
      {
        key: "profile",
        status: status(!!(p.date_of_birth && p.bio && p.years_experience !== null && p.age_groups.length && p.languages.length && has("photo"))),
      },
      { key: "identity_documents", status: status(has("government_id") && has("college_or_work_id")) },
      { key: "health_disclosure", status: status(state.healthSaved, "done") },
      // Optional (2026-11-13): none given counts as done.
      { key: "references", status: state.references.length ? "waiting" : "done" },
      { key: "payout", status: status(!!state["payout-details"].method, "done") },
      { key: "psych_test", status: "to_do" },
    ];
    return { items, live: false };
  }
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    if (path === "/sitter/profile" && init?.method === "PUT") {
      state.profile = { ...state.profile, ...JSON.parse(init.body as string) };
      return Promise.resolve(jsonResponse(state.profile));
    }
    if (path === "/sitter/health-disclosure" && init?.method === "PUT") {
      state["health-disclosure"] = JSON.parse(init.body as string);
      state.healthSaved = true;
      return Promise.resolve(jsonResponse(state["health-disclosure"]));
    }
    if (path === "/sitter/payout-details" && init?.method === "PUT") {
      const body = JSON.parse(init.body as string);
      state["payout-details"] = {
        method: body.method,
        account_holder_name: body.account_holder_name ?? null,
        account_number: body.account_number ?? null,
        ifsc_code: body.ifsc_code ?? null,
        upi_id: body.upi_id ?? null,
      };
      return Promise.resolve(jsonResponse(state["payout-details"]));
    }
    if (path === "/sitter/references" && init?.method === "POST") {
      const body = JSON.parse(init.body as string);
      if (body.phone === "9876500000") {
        return Promise.resolve(
          jsonResponse({ error: { code: "reference_number_used", message: "You've already given that number" } }, 422),
        );
      }
      if (state.references.length >= 1) {
        return Promise.resolve(
          jsonResponse({ error: { code: "too_many_references", message: "Only two references are needed" } }, 409),
        );
      }
      const reference = { id: `ref-${state.references.length}`, outcome: "pending", ...body };
      state.references = [...state.references, reference];
      return Promise.resolve(jsonResponse(reference, 201));
    }
    if (/^\/sitter\/references\/[^/]+$/.test(path) && init?.method === "DELETE") {
      const id = path.split("/").pop();
      state.references = state.references.filter((r) => (r as { id: string }).id !== id);
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (path.startsWith("/documents/mine")) {
      const type = new URLSearchParams(path.split("?")[1]).get("type") ?? "";
      const uploaded = state.documents.includes(type) ? [{ id: `doc-${type}`, type, child_id: null, status: "uploaded" }] : [];
      return Promise.resolve(jsonResponse(uploaded));
    }
    if (path.endsWith("/sitter/checklist")) return Promise.resolve(jsonResponse(checklist()));
    if (path.endsWith("/sitter/profile")) return Promise.resolve(jsonResponse(state.profile));
    if (path.endsWith("/sitter/health-disclosure")) return Promise.resolve(jsonResponse(state["health-disclosure"]));
    if (path.endsWith("/sitter/payout-details")) return Promise.resolve(jsonResponse(state["payout-details"]));
    if (path.endsWith("/sitter/references")) return Promise.resolve(jsonResponse(state.references));
    return Promise.reject(new Error(`unexpected request: ${init?.method ?? "GET"} ${path}`));
  }) as typeof fetch);
  return calls;
}

async function clickContinue(name = "Continue") {
  fireEvent.click(await screen.findByRole("button", { name }));
}

async function fillProfileAndContinue() {
  fireEvent.change(await screen.findByLabelText("Date of birth"), { target: { value: "1995-06-15" } });
  fireEvent.change(screen.getByLabelText("Years of experience"), { target: { value: "5" } });
  fireEvent.change(screen.getByLabelText(/About you/), { target: { value: "I love storytime." } });
  fireEvent.click(screen.getByRole("button", { name: /Toddler/ }));
  fireEvent.click(screen.getByRole("button", { name: "English" }));
  await clickContinue();
  await screen.findByRole("heading", { name: "ID verification" });
}

async function addAReference() {
  const section = (await screen.findByRole("heading", { name: "References" })).closest("section")!;
  const scope = within(section);
  fireEvent.change(scope.getByLabelText("Name"), { target: { value: "Priya Rao" } });
  fireEvent.change(scope.getByLabelText("Relationship"), { target: { value: "Neighbour" } });
  fireEvent.change(scope.getByLabelText("Mobile number"), { target: { value: "9876543210" } });
  fireEvent.click(scope.getByRole("button", { name: "Add this reference" }));
  await waitFor(() => expect(scope.queryByText("Priya Rao")).toBeTruthy());
  return scope;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("the sitter application page", () => {
  test("starts at About you, step 3 of her 8, with a bar of how many are done", async () => {
    mockApi();
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Your application" })).toBeTruthy();
    expect(await screen.findByText(/Step 3 of 8/)).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Steps done" }).getAttribute("aria-valuetext")).toBe(
      "4 of 8 steps done", // consent, details, ID verification (the mock's uploads) and references (optional)
    );
    expect(await screen.findByRole("heading", { name: "Your profile" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "ID verification" })).toBeNull();
    // Back is there from the first step too: it goes to "Your profile".
    expect(await screen.findByRole("button", { name: "← Back" })).toBeTruthy();
  });

  test("completing About you sends the right body and advances to ID verification", async () => {
    const calls = mockApi();
    renderPage();
    await fillProfileAndContinue();

    const put = calls.find((call) => call.url.endsWith("/sitter/profile") && call.init?.method === "PUT")!;
    expect(JSON.parse(put.init!.body as string)).toEqual({
      date_of_birth: "1995-06-15",
      bio: "I love storytime.",
      years_experience: 5,
      age_groups: ["Toddler"],
      languages: ["English"],
      first_aid: false,
      reference_shared_consent: false,
    });
    expect(await screen.findByText(/Step 4 of 8/)).toBeTruthy();
  });

  test("ages and languages are picked from fixed lists, and every field says what's missing", async () => {
    // UX review 2026-11-13: free text showed parents "dsfghjkl"; errors name the field.
    const calls = mockApi();
    renderPage();
    expect(await screen.findByRole("button", { name: /Preschool \(3–5\)/ })).toBeTruthy();
    for (const language of ["English", "Kannada", "Hindi", "Tamil", "Malayalam", "Telugu"]) {
      expect(screen.getByRole("button", { name: language }).getAttribute("aria-pressed")).toBe("false");
    }
    expect(screen.queryByRole("button", { name: /Infant/ })).toBeNull(); // Pacifyco starts at 18 months
    await clickContinue();
    expect(await screen.findByText("Please write a few words for parents.")).toBeTruthy();
    expect(screen.getByText("Please choose at least one age group.")).toBeTruthy();
    expect(screen.getByText("Please choose at least one language.")).toBeTruthy();
    expect(calls.some((call) => call.init?.method === "PUT")).toBe(false);
  });

  test("her photo is part of About you, JPG or PNG only, and required", async () => {
    const calls = mockApi({ documents: ["government_id", "college_or_work_id"] });
    renderPage();
    const label = await screen.findByText("Profile photo");
    const input = document.getElementById(label.getAttribute("for")!) as HTMLInputElement;
    expect(input.accept).toBe(".jpg,.jpeg,.png,image/jpeg,image/png");
    fireEvent.change(screen.getByLabelText("Date of birth"), { target: { value: "1995-06-15" } });
    fireEvent.change(screen.getByLabelText("Years of experience"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText(/About you/), { target: { value: "I love storytime." } });
    fireEvent.click(screen.getByRole("button", { name: /Toddler/ }));
    fireEvent.click(screen.getByRole("button", { name: "English" }));
    await clickContinue();
    expect(await screen.findByText("Please add your photo.")).toBeTruthy();
    expect(calls.some((call) => call.init?.method === "PUT")).toBe(false);
  });

  test("ID verification needs both IDs; the police certificate can come later", async () => {
    mockApi({ profile: FILLED_PROFILE, documents: ["photo"] });
    renderPage("/sitter/application?step=documents");
    expect(await screen.findByRole("heading", { name: "ID verification" })).toBeTruthy();
    expect(screen.getByText(/Police clearance certificate \(optional for now\)/)).toBeTruthy();
    expect(screen.queryByText("First-aid certificate")).toBeNull(); // only if she's first-aid certified
    await clickContinue();
    expect(await screen.findByText("Please add your government ID and a college or work ID to continue.")).toBeTruthy();
  });

  test("a step after one still to do is locked, and leads to the one to do", async () => {
    mockApi();
    renderPage("/sitter/application?step=payout");
    expect(await screen.findByRole("heading", { name: 'Finish "About you" first' })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Go to About you/ }).getAttribute("href")).toBe(
      "/sitter/application?step=profile",
    );
    expect(screen.queryByLabelText("UPI ID")).toBeNull();
  });

  test("the checklist can open a step directly", async () => {
    mockApi(UP_TO_REFERENCES);
    renderPage("/sitter/application?step=references");
    expect(await screen.findByRole("heading", { name: "References" })).toBeTruthy();
    expect(screen.getByText(/Step 6 of 8/)).toBeTruthy();
  });

  test("there is no reference-sharing tick under first aid (Reuben, 2026-11-13)", async () => {
    mockApi();
    renderPage();
    expect(await screen.findByRole("checkbox", { name: /first-aid certified/ })).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: /references/ })).toBeNull();
  });

  test("the back button returns to the previous step", async () => {
    mockApi();
    renderPage();
    await fillProfileAndContinue();

    fireEvent.click(await screen.findByRole("button", { name: "← Back" }));
    expect(await screen.findByRole("heading", { name: "Your profile" })).toBeTruthy();
    expect(await screen.findByText(/Step 3 of 8/)).toBeTruthy();
  });

  test("walking through every step reaches the psychology screening page", async () => {
    mockApi();
    const router = createMemoryRouter(
      [
        { path: "/", element: <SitterApplicationPage /> },
        { path: "/sitter/psych-test", element: <p>Psychology screening page</p> },
      ],
      { initialEntries: ["/"] },
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </QueryClientProvider>,
    );

    await fillProfileAndContinue();
    await clickContinue(); // ID verification: both IDs are in (the mock)
    await screen.findByText(/Step 5 of 8/);
    await clickContinue(); // health disclosure: nothing to declare is fine
    await screen.findByText(/Step 6 of 8/);
    await clickContinue(); // references: optional, none added
    await screen.findByText(/Step 7 of 8/);
    fireEvent.change(await screen.findByLabelText("UPI ID"), { target: { value: "asha@upi" } });
    await clickContinue("Continue to the psychology screening");

    expect(await screen.findByText("Psychology screening page")).toBeTruthy();
  });

  test("a reference is optional: 1 person, and she can continue without one", async () => {
    // Reuben, 2026-11-13: optional but good to have.
    mockApi(UP_TO_REFERENCES);
    renderPage("/sitter/application?step=references");
    await screen.findByRole("heading", { name: "References" });
    expect(screen.getByText(/1 person who can vouch for you. Optional/)).toBeTruthy();
    await clickContinue();
    expect(await screen.findByText(/Step 7 of 8/)).toBeTruthy();
  });

  test("a number she has given before is refused, on the number field", async () => {
    mockApi(UP_TO_REFERENCES);
    renderPage("/sitter/application?step=references");
    const section = (await screen.findByRole("heading", { name: "References" })).closest("section")!;
    const scope = within(section);
    fireEvent.change(scope.getByLabelText("Name"), { target: { value: "Priya Rao" } });
    fireEvent.change(scope.getByLabelText("Relationship"), { target: { value: "Neighbour" } });
    fireEvent.change(scope.getByLabelText("Mobile number"), { target: { value: "9876500000" } });
    fireEvent.click(scope.getByRole("button", { name: "Add this reference" }));
    expect(await scope.findByText("You've already given that number. Please give a different one.")).toBeTruthy();
  });

  test("a second reference isn't asked for", async () => {
    mockApi(UP_TO_REFERENCES);
    renderPage("/sitter/application?step=references");
    const scope = await addAReference();
    expect(scope.queryByLabelText("Name")).toBeNull(); // the add form hides once one is added
    expect(scope.getByRole("button", { name: "Continue" })).toBeTruthy();
  });
});
