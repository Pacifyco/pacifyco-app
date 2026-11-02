import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { SitterApplicationPage } from "./SitterApplicationPage";

// Needs no sign-in session to render, same as FamilyPage: apiFetch sends no Authorization header
// when there isn't one, and every test here stubs fetch by URL directly.
function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SitterApplicationPage />
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
      hourly_rate_paise: null,
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

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("the sitter application page", () => {
  test("shows every section before anything is filled in", async () => {
    mockApi();
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Your application" })).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Your profile" })).toBeTruthy();
    expect(await screen.findByText("Application in progress")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Health disclosure" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Payout details" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "References" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Documents" })).toBeTruthy();
  });

  test("saving the profile sends the right body", async () => {
    const calls = mockApi();
    renderPage();
    await screen.findByRole("heading", { name: "Your profile" });

    fireEvent.change(screen.getByLabelText("Date of birth"), { target: { value: "1995-06-15" } });
    fireEvent.change(screen.getByLabelText("Years of experience"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText(/About you/), { target: { value: "I love looking after kids." } });
    fireEvent.change(screen.getByLabelText("Age groups you care for"), { target: { value: "Toddler, Preschool" } });
    fireEvent.change(screen.getByLabelText("Languages you speak"), { target: { value: "English, Kannada" } });
    fireEvent.change(screen.getByLabelText(/Hourly rate/), { target: { value: "100" } });
    fireEvent.click(screen.getByLabelText("I'm first-aid certified"));
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() =>
      expect(calls.some((call) => call.url.endsWith("/sitter/profile") && call.init?.method === "PUT")).toBe(true),
    );
    const put = calls.find((call) => call.url.endsWith("/sitter/profile") && call.init?.method === "PUT")!;
    expect(JSON.parse(put.init!.body as string)).toEqual({
      date_of_birth: "1995-06-15",
      bio: "I love looking after kids.",
      years_experience: 5,
      age_groups: ["Toddler", "Preschool"],
      languages: ["English", "Kannada"],
      first_aid: true,
      hourly_rate_paise: 10_000,
    });
  });

  test("saving the health disclosure", async () => {
    const calls = mockApi();
    renderPage();
    await screen.findByRole("heading", { name: "Health disclosure" });

    fireEvent.change(await screen.findByLabelText(/Health disclosure/), { target: { value: "Mild peanut allergy." } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(
        calls.some((call) => call.url.endsWith("/sitter/health-disclosure") && call.init?.method === "PUT"),
      ).toBe(true),
    );
    const put = calls.find((call) => call.url.endsWith("/sitter/health-disclosure") && call.init?.method === "PUT")!;
    expect(JSON.parse(put.init!.body as string)).toEqual({ disclosure: "Mild peanut allergy." });
  });

  test("saving payout details defaults to UPI", async () => {
    const calls = mockApi();
    renderPage();
    const section = (await screen.findByRole("heading", { name: "Payout details" })).closest("section")!;
    const scope = within(section);

    fireEvent.change(await scope.findByLabelText("UPI ID"), { target: { value: "asha@upi" } });
    fireEvent.click(scope.getByRole("button", { name: "Save payout details" }));

    await waitFor(() =>
      expect(calls.some((call) => call.url.endsWith("/sitter/payout-details") && call.init?.method === "PUT")).toBe(
        true,
      ),
    );
    const put = calls.find((call) => call.url.endsWith("/sitter/payout-details") && call.init?.method === "PUT")!;
    expect(JSON.parse(put.init!.body as string)).toEqual({ method: "upi", upi_id: "asha@upi" });
  });

  test("switching payout method to bank sends bank fields", async () => {
    const calls = mockApi();
    renderPage();
    const section = (await screen.findByRole("heading", { name: "Payout details" })).closest("section")!;
    const scope = within(section);

    fireEvent.change(await scope.findByLabelText("Payout method"), { target: { value: "bank" } });
    fireEvent.change(scope.getByLabelText("Account holder name"), { target: { value: "Asha Rao" } });
    fireEvent.change(scope.getByLabelText("Account number"), { target: { value: "123456789012" } });
    fireEvent.change(scope.getByLabelText("IFSC code"), { target: { value: "hdfc0000123" } });
    fireEvent.click(scope.getByRole("button", { name: "Save payout details" }));

    await waitFor(() =>
      expect(calls.some((call) => call.url.endsWith("/sitter/payout-details") && call.init?.method === "PUT")).toBe(
        true,
      ),
    );
    const put = calls.find((call) => call.url.endsWith("/sitter/payout-details") && call.init?.method === "PUT")!;
    expect(JSON.parse(put.init!.body as string)).toEqual({
      method: "bank",
      account_holder_name: "Asha Rao",
      account_number: "123456789012",
      ifsc_code: "HDFC0000123",
    });
  });

  test("adding two references hides the add form, and removing one brings it back", async () => {
    mockApi();
    renderPage();
    const section = (await screen.findByRole("heading", { name: "References" })).closest("section")!;
    const scope = within(section);

    fireEvent.change(scope.getByLabelText("Name"), { target: { value: "Priya Rao" } });
    fireEvent.change(scope.getByLabelText("Relationship"), { target: { value: "Neighbour" } });
    fireEvent.change(scope.getByLabelText("Phone"), { target: { value: "9876543210" } });
    fireEvent.click(scope.getByRole("button", { name: "Add reference" }));
    expect(await scope.findByText("Priya Rao")).toBeTruthy();

    fireEvent.change(scope.getByLabelText("Name"), { target: { value: "Vikram Rao" } });
    fireEvent.change(scope.getByLabelText("Relationship"), { target: { value: "Former employer" } });
    fireEvent.change(scope.getByLabelText("Phone"), { target: { value: "9876500000" } });
    fireEvent.click(scope.getByRole("button", { name: "Add reference" }));
    expect(await scope.findByText("Vikram Rao")).toBeTruthy();

    await waitFor(() => expect(scope.queryByRole("button", { name: "Add reference" })).toBeNull());

    fireEvent.click(scope.getByRole("button", { name: "Remove Priya Rao" }));
    await waitFor(() => expect(scope.queryByText("Priya Rao")).toBeNull());
    expect(scope.getByRole("button", { name: "Add reference" })).toBeTruthy();
  });

  test("documents section has an upload slot for each sitter document", async () => {
    mockApi();
    renderPage();
    await screen.findByRole("heading", { name: "Documents" });
    expect(screen.getByLabelText("Government ID")).toBeTruthy();
    expect(screen.getByLabelText("College or work ID")).toBeTruthy();
    expect(screen.getByLabelText("Police clearance certificate")).toBeTruthy();
    expect(screen.getByLabelText("First-aid certificate")).toBeTruthy();
  });
});
