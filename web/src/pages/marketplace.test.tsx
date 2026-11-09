import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { hourLabel, kolkataTime } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import { AvailabilityPage } from "./AvailabilityPage";
import { FindSittersPage } from "./FindSittersPage";
import { SitterProfilePage } from "./SitterProfilePage";

type Call = { method: string; path: string; body: unknown };
type Handler = (body: unknown) => Response;

function mockApi(routes: Record<string, Handler>) {
  const calls: Call[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const method = init?.method ?? "GET";
    const body = init?.body ? (JSON.parse(init.body as string) as unknown) : null;
    calls.push({ method, path, body });
    const handler = routes[`${method} ${path}`] ?? routes[`${method} ${path.split("?")[0]}`];
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
          <Route path="/sitter/availability" element={<AvailabilityPage />} />
          <Route path="/parent/sitters" element={<FindSittersPage />} />
          <Route path="/parent/sitters/:sitterId" element={<SitterProfilePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const error = (code: string, message: string, status: number) =>
  jsonResponse({ error: { code, message, details: null } }, status);

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("times in Kolkata", () => {
  test("a day and an hour become UTC", () => {
    expect(kolkataTime("2026-11-10", 9)).toBe("2026-11-10T03:30:00.000Z");
    expect(kolkataTime("2026-11-10", 24)).toBe("2026-11-10T18:30:00.000Z"); // midnight at the end of the day
  });

  test("hours read naturally", () => {
    expect(hourLabel(9)).toBe("9:00 am");
    expect(hourLabel(12)).toBe("12:00 pm (noon)");
    expect(hourLabel(18)).toBe("6:00 pm");
    expect(hourLabel(24)).toBe("12:00 am (midnight)");
  });
});

describe("a sitter's availability", () => {
  const SLOT = { id: "t1", starts_at: "2026-11-10T03:30:00Z", ends_at: "2026-11-10T07:30:00Z" };

  test("lists her free times and removes one", async () => {
    const calls = mockApi({
      "GET /sitter/availability": () => jsonResponse([SLOT]),
      "DELETE /sitter/availability/t1": () => new Response(null, { status: 204 }),
    });
    renderAt("/sitter/availability");
    expect(await screen.findByText("Tue, 10 Nov · 9:00 am – 1:00 pm")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove Tue, 10 Nov · 9:00 am – 1:00 pm" }));
    await waitFor(() => expect(calls).toContainEqual({ method: "DELETE", path: "/sitter/availability/t1", body: null }));
  });

  test("adding a time sends it in UTC", async () => {
    const calls = mockApi({
      "GET /sitter/availability": () => jsonResponse([]),
      "POST /sitter/availability": () => jsonResponse(SLOT, 201),
    });
    renderAt("/sitter/availability");
    expect(await screen.findByText(/No free times yet/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Day"), { target: { value: "2026-11-10" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "9" } });
    fireEvent.change(screen.getByLabelText("Until"), { target: { value: "13" } });
    fireEvent.click(screen.getByRole("button", { name: "Add this time" }));
    await waitFor(() =>
      expect(calls).toContainEqual({
        method: "POST",
        path: "/sitter/availability",
        body: { starts_at: "2026-11-10T03:30:00.000Z", ends_at: "2026-11-10T07:30:00.000Z" },
      }),
    );
  });

  test("a day is needed, and the API's reason is shown", async () => {
    mockApi({
      "GET /sitter/availability": () => jsonResponse([]),
      "POST /sitter/availability": () => error("slot_overlaps", "This overlaps a time you've already added", 409),
    });
    renderAt("/sitter/availability");
    fireEvent.click(await screen.findByRole("button", { name: "Add this time" }));
    expect(screen.getByText("Please choose a day.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Day"), { target: { value: "2026-11-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Add this time" }));
    expect(await screen.findByText("This overlaps a time you've already added")).toBeTruthy();
  });
});

describe("finding a sitter", () => {
  const LAKSHMI = {
    id: "s1",
    full_name: "Lakshmi Nair",
    years_experience: 4,
    age_groups: ["Ages 2–5"],
    languages: ["English", "Kannada"],
    first_aid: true,
    avg_rating: null,
    review_count: 0,
    distance_km: 2.37,
    photo_url: "https://storage.example/photo/s1?token=x",
    plan: "pause",
  };

  test("each card shows the plan the sitter works, as a small label with no price", async () => {
    mockApi({
      "GET /parent/sitters": () =>
        jsonResponse([LAKSHMI, { ...LAKSHMI, id: "s2", full_name: "Meena Rao", plan: "recharge" }]),
    });
    renderAt("/parent/sitters");
    const lakshmi = within((await screen.findByRole("heading", { name: "Lakshmi Nair" })).closest("article")!);
    const meena = within(screen.getByRole("heading", { name: "Meena Rao" }).closest("article")!);
    // Seen as "Pause"; screen readers hear "Works the Pause plan".
    expect(lakshmi.getByText("Pause").textContent).toBe("Works the Pause plan");
    expect(meena.getByText("Recharge").textContent).toBe("Works the Recharge plan");
  });

  test("lists every live sitter (no plan filter) with no prices, and the intro beside Home", async () => {
    const calls = mockApi({ "GET /parent/sitters": () => jsonResponse([LAKSHMI]) });
    const { container } = renderAt("/parent/sitters");
    const card = within((await screen.findByRole("heading", { name: "Lakshmi Nair" })).closest("article")!);
    expect(card.getByText("4 years' experience · 2.4 km away")).toBeTruthy();
    expect(card.getByRole("img", { name: "Lakshmi Nair" }).getAttribute("src")).toBe(
      "https://storage.example/photo/s1?token=x",
    );
    expect(card.getByText("First-aid certified")).toBeTruthy();
    expect(card.queryByText("Psychology screening passed")).toBeNull(); // placeholder questions for now
    expect(card.getByRole("link", { name: "See Lakshmi's profile" }).getAttribute("href")).toBe("/parent/sitters/s1");
    expect(container.textContent).not.toMatch(/₹|per hour|\/hour/);
    expect(calls[0]!.path).toBe("/parent/sitters?sort=distance");
    // Only day, language, sort and first aid: no plan, time, experience or rating filters, no search button.
    for (const gone of ["Plan", "From", "Until", "Experience", "Rating"]) expect(screen.queryByLabelText(gone)).toBeNull();
    expect(screen.queryByRole("button", { name: /Show sitters/ })).toBeNull();
    const heading = screen.getByRole("heading", { level: 1, name: "Find a sitter" });
    expect(heading.closest("div")!.parentElement!.contains(screen.getByRole("link", { name: "Home" }))).toBe(true);
  });

  test("language options come from the sitters' own languages", async () => {
    mockApi({
      "GET /parent/sitters": () =>
        jsonResponse([LAKSHMI, { ...LAKSHMI, id: "s2", full_name: "Meena", languages: ["kannada", "Tamil "] }]),
    });
    renderAt("/parent/sitters");
    await screen.findByRole("heading", { name: "Meena" });
    const options = within(screen.getByLabelText("Speaks")).getAllByRole("option").map((option) => option.textContent);
    expect(options).toEqual(["Any", "English", "Kannada", "Tamil"]);
  });

  test("each filter applies straight away", async () => {
    const calls = mockApi({ "GET /parent/sitters": () => jsonResponse([LAKSHMI]) });
    renderAt("/parent/sitters");
    await screen.findByRole("heading", { name: "Lakshmi Nair" });

    fireEvent.change(screen.getByLabelText(/Day/), { target: { value: "2026-11-10" } });
    fireEvent.change(screen.getByLabelText("Speaks"), { target: { value: "Kannada" } });
    fireEvent.click(screen.getByLabelText("First-aid certified only"));
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "rating" } });

    await waitFor(() => expect(calls.at(-1)!.path).toContain("sort=rating"));
    const params = new URLSearchParams(calls.at(-1)!.path.split("?")[1]);
    expect(Object.fromEntries(params)).toEqual({
      sort: "rating",
      day: "2026-11-10",
      language: "Kannada",
      first_aid: "true",
    });
  });

  test("no match says so", async () => {
    mockApi({ "GET /parent/sitters": () => jsonResponse([]) });
    renderAt("/parent/sitters");
    expect(await screen.findByText("No sitters match. Try another day or fewer filters.")).toBeTruthy();
  });

  test("a parent who hasn't finished their profile is sent to finish it", async () => {
    mockApi({ "GET /parent/sitters": () => error("profile_unfinished", "Please finish your profile", 409) });
    renderAt("/parent/sitters");
    expect(await screen.findByText(/Finish your profile first/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Finish your profile/ }).getAttribute("href")).toBe("/parent/profile");
  });
});

describe("a sitter's profile page", () => {
  const DETAIL = {
    id: "s1",
    full_name: "Lakshmi Nair",
    years_experience: 4,
    age_groups: ["Ages 2–5"],
    languages: ["English", "Tamil"],
    first_aid: false,
    avg_rating: 4.8,
    review_count: 12,
    distance_km: 0.4,
    photo_url: null,
    bio: "I love storytime.",
    plan: "pause",
    free_times: [{ starts_at: "2026-11-10T03:30:00Z", ends_at: "2026-11-10T07:30:00Z" }],
    reference: null,
  };

  test("shows who she is, when she's free and the 1-hour nudge, with no price", async () => {
    mockApi({ "GET /parent/sitters/s1": () => jsonResponse(DETAIL) });
    const { container } = renderAt("/parent/sitters/s1");
    expect(await screen.findByRole("heading", { level: 1, name: "Lakshmi Nair" })).toBeTruthy();
    expect(screen.getByText("4 years' experience · under 1 km away · Speaks English, Tamil")).toBeTruthy();
    expect(screen.getByText("I love storytime.")).toBeTruthy();
    expect(screen.getByText("Tue, 10 Nov · 9:00 am – 1:00 pm")).toBeTruthy();
    expect(screen.getByText(/Start with a 1-hour booking while you're at home/)).toBeTruthy();
    expect(screen.queryByText("First-aid certified")).toBeNull();
    expect(container.textContent).not.toMatch(/₹|per hour|\/hour/);
  });

  test("a Recharge sitter's shared reference is shown; others have none", async () => {
    const reference = { name: "Asha Rao", phone: "+919876500000", relationship: "Former employer" };
    mockApi({ "GET /parent/sitters/s1": () => jsonResponse({ ...DETAIL, plan: "recharge", reference }) });
    renderAt("/parent/sitters/s1");
    expect(await screen.findByRole("heading", { name: "A reference for Lakshmi" })).toBeTruthy();
    expect(screen.getByText("Asha Rao · Former employer")).toBeTruthy();
    expect(screen.getByRole("link", { name: "+919876500000" }).getAttribute("href")).toBe("tel:+919876500000");
  });

  test("no reference card without a shared reference", async () => {
    mockApi({ "GET /parent/sitters/s1": () => jsonResponse(DETAIL) });
    renderAt("/parent/sitters/s1");
    await screen.findByRole("heading", { level: 1, name: "Lakshmi Nair" });
    expect(screen.queryByRole("heading", { name: /A reference for/ })).toBeNull();
  });

  test("a sitter who isn't available says so", async () => {
    mockApi({ "GET /parent/sitters/s9": () => error("not_found", "That sitter isn't available", 404) });
    renderAt("/parent/sitters/s9");
    expect(await screen.findByText("This sitter isn't available right now.")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Find a sitter/ })).toBeTruthy();
  });
});
