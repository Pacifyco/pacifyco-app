import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { AuthProvider } from "../auth/AuthProvider";
import { jsonResponse } from "../test/renderApp";
import { ageText, FamilyPage } from "./FamilyPage";

// FamilyPage needs no sign-in session to render: apiFetch just sends no Authorization header when
// there isn't one (lib/supabase.ts), and every test here stubs fetch by URL directly. Wrapped in a
// MemoryRouter because the last step navigates to the parent home page.
function renderFamilyPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <MemoryRouter>
          <FamilyPage />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

const CONSENTED = { version: "x", required_accepted: true, accepted_at: "2026-11-01T10:00:00Z", marketing: false };

/** Fills the day, month and year selects. */
function chooseBirthday(day: string, month: string, year: string) {
  fireEvent.change(screen.getByLabelText("Day"), { target: { value: day } });
  fireEvent.change(screen.getByLabelText("Month"), { target: { value: month } });
  fireEvent.change(screen.getByLabelText("Year"), { target: { value: year } });
}

type Call = { url: string; init?: RequestInit };

function mockApi(overrides: Record<string, unknown> = {}) {
  const calls: Call[] = [];
  const state = {
    children: [] as unknown[],
    "emergency-contacts": [] as unknown[],
    "authorised-adults": [] as unknown[],
    consent: CONSENTED as unknown,
    ...overrides,
  };
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    if (path === "/parent/children" && init?.method === "POST") {
      const body = JSON.parse(init.body as string);
      const child = { id: `child-${state.children.length}`, verification_status: "pending", ...body };
      state.children = [...state.children, child];
      return Promise.resolve(jsonResponse(child, 201));
    }
    if (/^\/parent\/children\/[^/]+$/.test(path) && init?.method === "DELETE") {
      const id = path.split("/").pop();
      state.children = state.children.filter((c) => (c as { id: string }).id !== id);
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (path === "/parent/emergency-contacts" && init?.method === "PUT") {
      const body = JSON.parse(init.body as string) as { contacts: unknown[] };
      state["emergency-contacts"] = body.contacts.map((c, i) => ({ id: `contact-${i}`, ...(c as object) }));
      return Promise.resolve(jsonResponse(state["emergency-contacts"]));
    }
    if (path === "/parent/authorised-adults" && init?.method === "POST") {
      const body = JSON.parse(init.body as string);
      // The API stores mobiles as +91 and ten digits.
      const adult = { id: `adult-${state["authorised-adults"].length}`, ...body, phone: `+91${body.phone}` };
      state["authorised-adults"] = [...state["authorised-adults"], adult];
      return Promise.resolve(jsonResponse(adult, 201));
    }
    if (/^\/parent\/authorised-adults\/[^/]+$/.test(path) && init?.method === "DELETE") {
      const id = path.split("/").pop();
      state["authorised-adults"] = state["authorised-adults"].filter((a) => (a as { id: string }).id !== id);
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (path === "/documents/mine" || path.startsWith("/documents/mine?")) {
      return Promise.resolve(jsonResponse([]));
    }
    if (path === "/parent/consent") return Promise.resolve(jsonResponse(state.consent));
    if (path.endsWith("/parent/children")) return Promise.resolve(jsonResponse(state.children));
    if (path.endsWith("/parent/emergency-contacts")) return Promise.resolve(jsonResponse(state["emergency-contacts"]));
    if (path.endsWith("/parent/authorised-adults")) return Promise.resolve(jsonResponse(state["authorised-adults"]));
    return Promise.reject(new Error(`unexpected request: ${init?.method ?? "GET"} ${path}`));
  }) as typeof fetch);
  return calls;
}

async function clickContinue() {
  fireEvent.click(await screen.findByRole("button", { name: "Continue" }));
}

const ASHA = { id: "child-0", name: "Asha", date_of_birth: "2023-05-01", verification_status: "pending" };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("the family page", () => {
  test("nothing about the family can be added before the consent", async () => {
    // UX review 2026-11-13: children's data waits for the parental consent.
    mockApi({ consent: { version: "x", required_accepted: false, accepted_at: null, marketing: false } });
    renderFamilyPage();
    expect(await screen.findByRole("heading", { name: "Your consent comes first" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Read the consent form/ }).getAttribute("href")).toBe("/parent/consent");
    expect(screen.queryByLabelText("Child's name")).toBeNull();
    expect(screen.queryByText(/Step 1 of 2/)).toBeNull();
  });

  test("starts on step 1 (your children) and shows nothing else yet", async () => {
    mockApi();
    renderFamilyPage();
    expect(await screen.findByRole("heading", { level: 1, name: "My family" })).toBeTruthy();
    expect(await screen.findByText(/Step 1 of 2/)).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("1");
    expect(await screen.findByText("You haven't added a child yet.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Emergency contacts" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Authorised adults" })).toBeNull();
    // Back is there from the first step too: it goes to "Your profile".
    expect(await screen.findByRole("button", { name: "← Back" })).toBeTruthy();
  });

  test("with no child yet, the form is open and Continue waits for one", async () => {
    mockApi();
    renderFamilyPage();
    expect(await screen.findByLabelText("Child's name")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Add a child to continue.")).toBeTruthy();
  });

  test("a child's name and date of birth are asked for by field", async () => {
    const calls = mockApi();
    renderFamilyPage();
    fireEvent.click(await screen.findByRole("button", { name: "Save" }));
    expect(await screen.findByText("Please enter your child's name.")).toBeTruthy();
    expect(screen.getByText("Please choose the day, month and year.")).toBeTruthy();
    expect(calls.some((call) => call.init?.method === "POST")).toBe(false);
  });

  test("adding a child shows it in the list and sends the right body", async () => {
    const calls = mockApi();
    renderFamilyPage();

    fireEvent.change(await screen.findByLabelText("Child's name"), { target: { value: "Asha" } });
    chooseBirthday("01", "05", "2023");
    fireEvent.change(screen.getByLabelText(/Allergies/), { target: { value: "Peanuts" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("heading", { level: 3, name: "Asha" })).toBeTruthy();
    const post = calls.find((call) => call.url.endsWith("/parent/children") && call.init?.method === "POST")!;
    expect(JSON.parse(post.init!.body as string)).toEqual({
      name: "Asha",
      date_of_birth: "2023-05-01",
      allergies: "Peanuts",
      medical_notes: null,
      routines: null,
    });
  });

  test("removing a child calls the delete endpoint", async () => {
    const calls = mockApi({ children: [ASHA] });
    renderFamilyPage();
    fireEvent.click(await screen.findByRole("button", { name: "Remove Asha" }));
    await waitFor(() =>
      expect(calls.some((call) => call.url.endsWith("/parent/children/child-0") && call.init?.method === "DELETE")).toBe(
        true,
      ),
    );
  });

  test("a rejected birth certificate says why and asks for a new one", async () => {
    mockApi({
      children: [
        {
          id: "child-0",
          name: "Asha",
          date_of_birth: "2023-05-01",
          verification_status: "rejected",
          rejection_reason: "The name doesn't match",
        },
        { id: "child-1", name: "Kabir", date_of_birth: "2021-05-01", verification_status: "approved", verified_at: "2026-11-13T06:00:00Z" },
      ],
    });
    renderFamilyPage();
    expect(
      await screen.findByText("Pacifyco couldn't accept this birth certificate. Please upload a new one below."),
    ).toBeTruthy();
    expect(screen.getByText("Reason: The name doesn't match")).toBeTruthy();
    expect(screen.getByText("Verified 13 Nov. The birth certificate has been deleted.")).toBeTruthy();
    // A verified child has nothing to upload: only the rejected one offers a file picker.
    expect(screen.getAllByRole("button", { name: /Choose file/ })).toHaveLength(1);
  });

  test("continuing from step 1 advances to the emergency contact", async () => {
    mockApi({ children: [ASHA] });
    renderFamilyPage();
    await screen.findByText(/Step 1 of 2/);
    await clickContinue();
    expect(await screen.findByText(/Step 2 of 2/)).toBeTruthy();
    expect(screen.getByText("Emergency contact", { selector: "span" })).toBeTruthy();
  });

  test("the back button returns to the previous step", async () => {
    mockApi({ children: [ASHA] });
    renderFamilyPage();
    await screen.findByText(/Step 1 of 2/);
    await clickContinue();
    await screen.findByText(/Step 2 of 2/);

    fireEvent.click(await screen.findByRole("button", { name: "← Back" }));
    expect(await screen.findByText(/Step 1 of 2/)).toBeTruthy();
  });

  async function emergencyFields() {
    const section = (await screen.findByRole("heading", { name: "Emergency contact" })).closest("section")!;
    const scope = within(section);
    await scope.findByLabelText("Name"); // wait for the saved contact before the form is seeded
    return {
      scope,
      name: scope.getByLabelText("Name"),
      relationship: scope.getByLabelText("Relationship"),
      phone: scope.getByLabelText("Mobile number"),
    };
  }

  test("the emergency contact says which field is wrong", async () => {
    const calls = mockApi({ children: [ASHA] });
    renderFamilyPage();
    await clickContinue(); // children
    const { scope, name, phone } = await emergencyFields();
    fireEvent.change(name, { target: { value: "Priya Rao" } });
    fireEvent.change(phone, { target: { value: "12345" } });
    fireEvent.click(scope.getByRole("button", { name: "Continue" }));

    expect(await scope.findByText("Please choose how you know them.")).toBeTruthy();
    expect(scope.getByText("Please enter a 10-digit mobile number.")).toBeTruthy();
    expect(calls.some((call) => call.init?.method === "PUT")).toBe(false);
  });

  test("one emergency contact is saved, and there are no authorised adults (Reuben, 2026-11-13)", async () => {
    const calls = mockApi({ children: [ASHA] });
    const router = createMemoryRouter(
      [
        { path: "/", element: <FamilyPage /> },
        { path: "/parent/profile", element: <p>Parent profile page</p> },
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
    await clickContinue(); // children

    const { scope, name, relationship, phone } = await emergencyFields();
    expect(scope.getAllByLabelText("Name")).toHaveLength(1);
    fireEvent.change(name, { target: { value: "Priya Rao" } });
    fireEvent.change(relationship, { target: { value: "Parent" } });
    fireEvent.change(phone, { target: { value: "9876543210" } });
    fireEvent.click(scope.getByRole("button", { name: "Continue" }));

    // It's the last step: back to the profile checklist.
    expect(await screen.findByText("Parent profile page")).toBeTruthy();
    const put = calls.find((call) => call.url.endsWith("/parent/emergency-contacts") && call.init?.method === "PUT")!;
    expect(JSON.parse(put.init!.body as string)).toEqual({
      contacts: [{ name: "Priya Rao", relationship: "Parent", phone: "9876543210" }],
    });
    expect(calls.some((call) => call.url.includes("authorised-adults"))).toBe(false);
  });

  test("the checklist can open a step directly", async () => {
    mockApi({ children: [ASHA] });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <MemoryRouter initialEntries={["/parent/family?step=emergency"]}>
            <FamilyPage />
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Step 2 of 2/)).toBeTruthy();
  });
});

describe("ageText", () => {
  test("months under two, years after", () => {
    const today = new Date("2026-11-13T12:00:00");
    expect(ageText("2025-05-01", today)).toBe("18 months old");
    expect(ageText("2022-05-01", today)).toBe("4 years old");
  });
});
