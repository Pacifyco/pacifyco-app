import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { FamilyPage } from "./FamilyPage";

// FamilyPage needs no sign-in session to render: apiFetch just sends no Authorization header when
// there isn't one (lib/supabase.ts), and every test here stubs fetch by URL directly. Wrapped in a
// MemoryRouter because the last step navigates to the parent home page.
function renderFamilyPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <FamilyPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

type Call = { url: string; init?: RequestInit };

function mockApi(overrides: Record<string, unknown> = {}) {
  const calls: Call[] = [];
  const state = {
    children: [] as unknown[],
    "emergency-contacts": [] as unknown[],
    "authorised-adults": [] as unknown[],
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
      const adult = { id: `adult-${state["authorised-adults"].length}`, ...body };
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

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("the family page", () => {
  test("starts on step 1 (your children) and shows nothing else yet", async () => {
    mockApi();
    renderFamilyPage();
    expect(await screen.findByRole("heading", { level: 1, name: "My family" })).toBeTruthy();
    expect(await screen.findByText("Step 1 of 3 · Your children")).toBeTruthy();
    expect(await screen.findByText("You haven't added a child yet.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Emergency contacts" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Authorised adults" })).toBeNull();
    expect(screen.queryByRole("button", { name: "← Back" })).toBeNull();
  });

  test("adding a child shows it in the list and sends the right body", async () => {
    const calls = mockApi();
    renderFamilyPage();
    fireEvent.click(await screen.findByRole("button", { name: "Add a child" }));

    fireEvent.change(screen.getByLabelText("Child's name"), { target: { value: "Asha" } });
    fireEvent.change(screen.getByLabelText("Date of birth"), { target: { value: "2023-05-01" } });
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
    const calls = mockApi({ children: [{ id: "child-0", name: "Asha", date_of_birth: "2023-05-01" }] });
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
        { id: "child-1", name: "Kabir", date_of_birth: "2021-05-01", verification_status: "approved" },
      ],
    });
    renderFamilyPage();
    expect(
      await screen.findByText("Pacify couldn't accept this birth certificate. Please upload a new one below."),
    ).toBeTruthy();
    expect(screen.getByText("Reason: The name doesn't match")).toBeTruthy();
    expect(screen.getByText("Verified. The birth certificate has been deleted.")).toBeTruthy();
  });

  test("continuing from step 1 advances to emergency contacts", async () => {
    mockApi();
    renderFamilyPage();
    await screen.findByText("Step 1 of 3 · Your children");
    await clickContinue();
    expect(await screen.findByText("Step 2 of 3 · Emergency contacts")).toBeTruthy();
  });

  test("the back button returns to the previous step", async () => {
    mockApi();
    renderFamilyPage();
    await screen.findByText("Step 1 of 3 · Your children");
    await clickContinue();
    await screen.findByText("Step 2 of 3 · Emergency contacts");

    fireEvent.click(screen.getByRole("button", { name: "← Back" }));
    expect(await screen.findByText("Step 1 of 3 · Your children")).toBeTruthy();
  });

  test("saving emergency contacts sends exactly two and advances", async () => {
    const calls = mockApi();
    renderFamilyPage();
    await clickContinue(); // children

    const section = (await screen.findByRole("heading", { name: "Emergency contacts" })).closest("section")!;
    const scope = within(section);
    await scope.findAllByLabelText("Name"); // wait for the contacts to load before the form is seeded
    const [firstName, secondName] = scope.getAllByLabelText("Name");
    const [firstRel, secondRel] = scope.getAllByLabelText("Relationship");
    const [firstPhone, secondPhone] = scope.getAllByLabelText("Phone");

    fireEvent.change(firstName, { target: { value: "Priya Rao" } });
    fireEvent.change(firstRel, { target: { value: "Mother" } });
    fireEvent.change(firstPhone, { target: { value: "9876543210" } });
    fireEvent.change(secondName, { target: { value: "Vikram Rao" } });
    fireEvent.change(secondRel, { target: { value: "Father" } });
    fireEvent.change(secondPhone, { target: { value: "9876500000" } });

    fireEvent.click(scope.getByRole("button", { name: "Continue" }));

    await waitFor(() =>
      expect(calls.some((call) => call.url.endsWith("/parent/emergency-contacts") && call.init?.method === "PUT")).toBe(
        true,
      ),
    );
    const put = calls.find((call) => call.url.endsWith("/parent/emergency-contacts") && call.init?.method === "PUT")!;
    const body = JSON.parse(put.init!.body as string);
    expect(body.contacts).toHaveLength(2);
    expect(body.contacts[0].name).toBe("Priya Rao");
    expect(body.contacts[1].name).toBe("Vikram Rao");

    expect(await screen.findByText("Step 3 of 3 · Authorised adults")).toBeTruthy();
  });

  test("adding and removing an authorised adult", async () => {
    mockApi();
    renderFamilyPage();
    await clickContinue(); // children
    await clickContinue(); // emergency contacts

    const heading = await screen.findByRole("heading", { name: "Authorised adults" });
    const section = heading.closest("section")!;

    fireEvent.change(within(section).getByLabelText("Name"), { target: { value: "Ravi K" } });
    fireEvent.change(within(section).getByLabelText("Relationship"), { target: { value: "Uncle" } });
    fireEvent.change(within(section).getByLabelText("Phone"), { target: { value: "9876500000" } });
    fireEvent.click(within(section).getByRole("button", { name: "Add" }));

    expect(await within(section).findByText("Ravi K")).toBeTruthy();

    fireEvent.click(within(section).getByRole("button", { name: "Remove Ravi K" }));
    await waitFor(() => expect(within(section).queryByText("Ravi K")).toBeNull());
  });

  test("finishing the last step navigates to the parent home page", async () => {
    mockApi();
    const router = createMemoryRouter(
      [
        { path: "/", element: <FamilyPage /> },
        { path: "/parent", element: <p>Parent home page</p> },
      ],
      { initialEntries: ["/"] },
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    await clickContinue(); // children
    await clickContinue(); // emergency contacts
    await screen.findByText("Step 3 of 3 · Authorised adults");
    await clickContinue(); // authorised adults, none required

    expect(await screen.findByText("Parent home page")).toBeTruthy();
  });
});
