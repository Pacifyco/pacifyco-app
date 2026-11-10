import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { SitterApplicationPage } from "./SitterApplicationPage";

// Needs no sign-in session to render, same as FamilyPage: apiFetch sends no Authorization header
// when there isn't one, and every test here stubs fetch by URL directly. Wrapped in a MemoryRouter
// because the last step navigates to the psychology screening page.
function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SitterApplicationPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

type Call = { url: string; init?: RequestInit };

function mockApi(overrides: Record<string, unknown> = {}) {
  const calls: Call[] = [];
  const state = {
    profile: {
      date_of_birth: null,
      bio: null,
      years_experience: null,
      age_groups: [] as string[],
      languages: [] as string[],
      first_aid: false,
      reference_shared_consent: false,
      onboarding_status: "in_progress",
    },
    "health-disclosure": { disclosure: null as string | null },
    "payout-details": {
      method: null as string | null,
      account_holder_name: null as string | null,
      account_number: null as string | null,
      ifsc_code: null as string | null,
      upi_id: null as string | null,
    },
    references: [] as unknown[],
    ...overrides,
  };
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    if (path === "/sitter/profile" && init?.method === "PUT") {
      state.profile = { ...state.profile, ...JSON.parse(init.body as string) };
      return Promise.resolve(jsonResponse(state.profile));
    }
    if (path === "/sitter/health-disclosure" && init?.method === "PUT") {
      state["health-disclosure"] = JSON.parse(init.body as string);
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
      if (state.references.length >= 2) {
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
    if (path === "/documents/mine" || path.startsWith("/documents/mine?")) {
      return Promise.resolve(jsonResponse([]));
    }
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
  await clickContinue();
  await screen.findByRole("heading", { name: "Documents" });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("the sitter application page", () => {
  test("starts on step 1 (about you) and shows nothing else yet", async () => {
    mockApi();
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Your application" })).toBeTruthy();
    expect(await screen.findByText("Step 1 of 5 · About you")).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Your profile" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Documents" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Health disclosure" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "References" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Payout details" })).toBeNull();
    // Back is there from the first step too: it goes to "Your profile".
    expect(await screen.findByRole("button", { name: "← Back" })).toBeTruthy();
  });

  test("completing the profile step sends the right body and advances to documents", async () => {
    const calls = mockApi();
    renderPage();
    await fillProfileAndContinue();

    const put = calls.find((call) => call.url.endsWith("/sitter/profile") && call.init?.method === "PUT")!;
    expect(JSON.parse(put.init!.body as string)).toEqual({
      date_of_birth: "1995-06-15",
      bio: null,
      years_experience: 5,
      age_groups: [],
      languages: [],
      first_aid: false,
      reference_shared_consent: false,
    });
    expect(await screen.findByText("Step 2 of 5 · Documents")).toBeTruthy();
  });

  test("sharing a reference with parents is unticked unless she ticks it", async () => {
    const calls = mockApi();
    renderPage();
    const tick = await screen.findByRole("checkbox", { name: /Pacify may show parents one of my references/ });
    expect((tick as HTMLInputElement).checked).toBe(false);
    fireEvent.click(tick);
    await fillProfileAndContinue();
    const put = calls.find((call) => call.url.endsWith("/sitter/profile") && call.init?.method === "PUT")!;
    expect(JSON.parse(put.init!.body as string).reference_shared_consent).toBe(true);
  });

  test("the documents step asks for a profile photo, JPG or PNG only", async () => {
    mockApi();
    renderPage();
    await fillProfileAndContinue();
    expect(screen.getByText("Profile photo")).toBeTruthy();
    const input = document.getElementById(screen.getByText("Profile photo").getAttribute("for")!) as HTMLInputElement;
    expect(input.accept).toBe(".jpg,.jpeg,.png,image/jpeg,image/png");
  });

  test("the back button returns to the previous step", async () => {
    mockApi();
    renderPage();
    await fillProfileAndContinue();

    fireEvent.click(await screen.findByRole("button", { name: "← Back" }));
    expect(await screen.findByRole("heading", { name: "Your profile" })).toBeTruthy();
    expect(await screen.findByText("Step 1 of 5 · About you")).toBeTruthy();
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
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await fillProfileAndContinue();

    await clickContinue(); // documents, nothing required
    await screen.findByText("Step 3 of 5 · Health disclosure");

    await clickContinue(); // health disclosure, blank is valid
    await screen.findByText("Step 4 of 5 · References");

    await clickContinue(); // references, none required
    await screen.findByText("Step 5 of 5 · Payout details");

    fireEvent.change(await screen.findByLabelText("UPI ID"), { target: { value: "asha@upi" } });
    await clickContinue("Continue to the psychology screening");

    expect(await screen.findByText("Psychology screening page")).toBeTruthy();
  });

  test("the payout step defaults to UPI and switches to bank fields", async () => {
    mockApi();
    renderPage();
    await fillProfileAndContinue();
    await clickContinue(); // documents
    await screen.findByText("Step 3 of 5 · Health disclosure");
    await clickContinue(); // health disclosure
    await screen.findByText("Step 4 of 5 · References");
    await clickContinue(); // references
    await screen.findByRole("heading", { name: "Payout details" });

    expect(await screen.findByLabelText("UPI ID")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Payout method"), { target: { value: "bank" } });
    expect(screen.queryByLabelText("UPI ID")).toBeNull();
    expect(screen.getByLabelText("Account holder name")).toBeTruthy();
  });

  test("a third reference is refused", async () => {
    mockApi();
    renderPage();
    await fillProfileAndContinue();
    await clickContinue(); // documents
    await screen.findByText("Step 3 of 5 · Health disclosure");
    await clickContinue(); // health disclosure
    const section = (await screen.findByRole("heading", { name: "References" })).closest("section")!;
    const scope = within(section);

    for (const name of ["Priya Rao", "Vikram Rao"]) {
      fireEvent.change(scope.getByLabelText("Name"), { target: { value: name } });
      fireEvent.change(scope.getByLabelText("Relationship"), { target: { value: "Neighbour" } });
      fireEvent.change(scope.getByLabelText("Phone"), { target: { value: "9876543210" } });
      fireEvent.click(scope.getByRole("button", { name: "Add reference" }));
      await waitFor(() => expect(scope.queryByText(name)).toBeTruthy());
    }
    expect(scope.queryByLabelText("Name")).toBeNull(); // the add form hides once two are added
    expect(scope.getByRole("button", { name: "Continue" })).toBeTruthy();
  });
});
