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
    expect(screen.queryByText(/Step 1 of 3/)).toBeNull();
  });

  test("starts on step 1 (your children) and shows nothing else yet", async () => {
    mockApi();
    renderFamilyPage();
    expect(await screen.findByRole("heading", { level: 1, name: "My family" })).toBeTruthy();
    expect(await screen.findByText(/Step 1 of 3/)).toBeTruthy();
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
      await screen.findByText("Pacify couldn't accept this birth certificate. Please upload a new one below."),
    ).toBeTruthy();
    expect(screen.getByText("Reason: The name doesn't match")).toBeTruthy();
    expect(screen.getByText("Verified 13 Nov. The birth certificate has been deleted.")).toBeTruthy();
    // A verified child has nothing to upload: only the rejected one offers a file picker.
    expect(screen.getAllByRole("button", { name: /Choose file/ })).toHaveLength(1);
  });

  test("continuing from step 1 advances to emergency contacts", async () => {
    mockApi({ children: [ASHA] });
    renderFamilyPage();
    await screen.findByText(/Step 1 of 3/);
    await clickContinue();
    expect(await screen.findByText(/Step 2 of 3/)).toBeTruthy();
    expect(screen.getByText("Emergency contacts", { selector: "span" })).toBeTruthy();
  });

  test("the back button returns to the previous step", async () => {
    mockApi({ children: [ASHA] });
    renderFamilyPage();
    await screen.findByText(/Step 1 of 3/);
    await clickContinue();
    await screen.findByText(/Step 2 of 3/);

    fireEvent.click(await screen.findByRole("button", { name: "← Back" }));
    expect(await screen.findByText(/Step 1 of 3/)).toBeTruthy();
  });

  async function emergencyFields() {
    const section = (await screen.findByRole("heading", { name: "Emergency contacts" })).closest("section")!;
    const scope = within(section);
    await scope.findAllByLabelText("Name"); // wait for the contacts to load before the form is seeded
    return { scope, names: scope.getAllByLabelText("Name"), relationships: scope.getAllByLabelText("Relationship"), phones: scope.getAllByLabelText("Mobile number") };
  }

  test("emergency contacts say which field is wrong, and need two different numbers", async () => {
    const calls = mockApi({ children: [ASHA] });
    renderFamilyPage();
    await clickContinue(); // children
    const { scope, names, relationships, phones } = await emergencyFields();
    fireEvent.change(names[0]!, { target: { value: "Priya Rao" } });
    fireEvent.change(relationships[0]!, { target: { value: "Parent" } });
    fireEvent.change(phones[0]!, { target: { value: "9876543210" } });
    fireEvent.change(names[1]!, { target: { value: "Vikram Rao" } });
    fireEvent.change(phones[1]!, { target: { value: "98765 43210" } });
    fireEvent.click(scope.getByRole("button", { name: "Continue" }));

    expect(await scope.findByText("Please choose how you know them.")).toBeTruthy();
    expect(scope.getByText("Please give two different numbers.")).toBeTruthy();
    expect(calls.some((call) => call.init?.method === "PUT")).toBe(false);
  });

  test("saving emergency contacts sends exactly two and advances", async () => {
    const calls = mockApi({ children: [ASHA] });
    renderFamilyPage();
    await clickContinue(); // children

    const { scope, names, relationships, phones } = await emergencyFields();
    expect(scope.getAllByText(/Required/).length).toBeGreaterThanOrEqual(2);
    fireEvent.change(names[0]!, { target: { value: "Priya Rao" } });
    fireEvent.change(relationships[0]!, { target: { value: "Parent" } });
    fireEvent.change(phones[0]!, { target: { value: "9876543210" } });
    fireEvent.change(names[1]!, { target: { value: "Vikram Rao" } });
    fireEvent.change(relationships[1]!, { target: { value: "Spouse" } });
    fireEvent.change(phones[1]!, { target: { value: "9876500000" } });

    fireEvent.click(scope.getByRole("button", { name: "Continue" }));

    await waitFor(() =>
      expect(calls.some((call) => call.url.endsWith("/parent/emergency-contacts") && call.init?.method === "PUT")).toBe(
        true,
      ),
    );
    const put = calls.find((call) => call.url.endsWith("/parent/emergency-contacts") && call.init?.method === "PUT")!;
    const body = JSON.parse(put.init!.body as string);
    expect(body.contacts).toHaveLength(2);
    expect(body.contacts[0]).toEqual({ name: "Priya Rao", relationship: "Parent", phone: "9876543210" });
    expect(body.contacts[1].name).toBe("Vikram Rao");

    expect(await screen.findByText(/Step 3 of 3/)).toBeTruthy();
  });

  const SAVED_CONTACTS = [
    { id: "c-0", name: "Priya Rao", relationship: "Parent", phone: "+919876543210" },
    { id: "c-1", name: "Vikram Rao", relationship: "Spouse", phone: "+919876500000" },
  ];

  test("adding and removing an authorised adult", async () => {
    mockApi({ children: [ASHA], "emergency-contacts": SAVED_CONTACTS });
    renderFamilyPage();
    await clickContinue(); // children
    await screen.findByDisplayValue("Priya Rao");
    await clickContinue(); // emergency contacts, already saved

    const heading = await screen.findByRole("heading", { name: "Authorised adults" });
    const section = heading.closest("section")!;

    fireEvent.change(within(section).getByLabelText("Name"), { target: { value: "Ravi K" } });
    fireEvent.change(within(section).getByLabelText("Relationship"), { target: { value: "Friend / Neighbour" } });
    fireEvent.change(within(section).getByLabelText("Mobile number"), { target: { value: "9876511111" } });
    fireEvent.click(within(section).getByRole("button", { name: "Add this person" }));

    expect(await within(section).findByText("Ravi K")).toBeTruthy();
    expect(within(section).getByText("Friend / Neighbour · +91 98765 11111")).toBeTruthy();

    fireEvent.click(within(section).getByRole("button", { name: "Remove Ravi K" }));
    await waitFor(() => expect(within(section).queryByText("Ravi K")).toBeNull());
  });

  test("finishing the last step goes back to the parent's profile checklist", async () => {
    mockApi({ children: [ASHA], "emergency-contacts": SAVED_CONTACTS });
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
    await screen.findByDisplayValue("Priya Rao");
    await clickContinue(); // emergency contacts
    await screen.findByText(/Step 3 of 3/);
    await clickContinue(); // authorised adults, none required

    expect(await screen.findByText("Parent profile page")).toBeTruthy();
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
    expect(await screen.findByText(/Step 2 of 3/)).toBeTruthy();
  });
});

describe("ageText", () => {
  test("months under two, years after", () => {
    const today = new Date("2026-11-13T12:00:00");
    expect(ageText("2025-05-01", today)).toBe("18 months old");
    expect(ageText("2022-05-01", today)).toBe("4 years old");
  });
});
