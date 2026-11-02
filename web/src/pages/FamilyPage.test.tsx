import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { FamilyPage } from "./FamilyPage";

// FamilyPage needs no sign-in session to render: apiFetch just sends no Authorization header when
// there isn't one (lib/supabase.ts), and every test here stubs fetch by URL directly.
function renderFamilyPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <FamilyPage />
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
    "single-parent-declaration": { declared: false },
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
    if (path.startsWith("/parent/single-parent-declaration") && init?.method === "PATCH") {
      state["single-parent-declaration"] = JSON.parse(init.body as string);
      return Promise.resolve(jsonResponse(state["single-parent-declaration"]));
    }
    if (path === "/documents/mine" || path.startsWith("/documents/mine?")) {
      return Promise.resolve(jsonResponse([]));
    }
    if (path.endsWith("/parent/children")) return Promise.resolve(jsonResponse(state.children));
    if (path.endsWith("/parent/emergency-contacts")) return Promise.resolve(jsonResponse(state["emergency-contacts"]));
    if (path.endsWith("/parent/authorised-adults")) return Promise.resolve(jsonResponse(state["authorised-adults"]));
    if (path.endsWith("/parent/single-parent-declaration")) {
      return Promise.resolve(jsonResponse(state["single-parent-declaration"]));
    }
    return Promise.reject(new Error(`unexpected request: ${init?.method ?? "GET"} ${path}`));
  }) as typeof fetch);
  return calls;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("the family page", () => {
  test("shows every section, empty, before anything is added", async () => {
    mockApi();
    renderFamilyPage();
    expect(await screen.findByRole("heading", { level: 1, name: "My family" })).toBeTruthy();
    expect(await screen.findByText("You haven't added a child yet.")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Emergency contacts" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Authorised adults" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Masked Aadhaar" })).toBeTruthy();
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

  test("saving emergency contacts sends exactly two", async () => {
    const calls = mockApi();
    renderFamilyPage();
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

    fireEvent.click(scope.getByRole("button", { name: "Save contacts" }));

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
  });

  test("adding and removing an authorised adult", async () => {
    mockApi();
    renderFamilyPage();
    await screen.findByRole("heading", { name: "Authorised adults" });
    const section = screen.getByRole("heading", { name: "Authorised adults" }).closest("section")!;

    fireEvent.change(within(section).getByLabelText("Name"), { target: { value: "Ravi K" } });
    fireEvent.change(within(section).getByLabelText("Relationship"), { target: { value: "Uncle" } });
    fireEvent.change(within(section).getByLabelText("Phone"), { target: { value: "9876500000" } });
    fireEvent.click(within(section).getByRole("button", { name: "Add" }));

    expect(await within(section).findByText("Ravi K")).toBeTruthy();

    fireEvent.click(within(section).getByRole("button", { name: "Remove Ravi K" }));
    await waitFor(() => expect(within(section).queryByText("Ravi K")).toBeNull());
  });

  test("ticking the single-parent declaration saves it", async () => {
    const calls = mockApi();
    renderFamilyPage();
    const checkbox = await screen.findByRole("checkbox", {
      name: "I'm the only parent or legal guardian of the children I add.",
    });
    expect((checkbox as HTMLInputElement).checked).toBe(false);
    fireEvent.click(checkbox);

    await waitFor(() =>
      expect(
        calls.some(
          (call) => call.url.endsWith("/parent/single-parent-declaration") && call.init?.method === "PATCH",
        ),
      ).toBe(true),
    );
  });
});
