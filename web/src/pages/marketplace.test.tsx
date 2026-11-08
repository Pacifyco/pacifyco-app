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
  };

  test("shows nearby sitters of the default plan, with no prices", async () => {
    const calls = mockApi({ "GET /parent/sitters": () => jsonResponse([LAKSHMI]) });
    const { container } = renderAt("/parent/sitters");
    const card = within((await screen.findByRole("heading", { name: "Lakshmi Nair" })).closest("article")!);
    expect(card.getByText("4 years' experience · 2.4 km away")).toBeTruthy();
    expect(card.getByText("First-aid certified")).toBeTruthy();
    expect(card.queryByText("Psychology screening passed")).toBeNull(); // placeholder questions for now
    expect(card.getByRole("link", { name: "See Lakshmi's profile" }).getAttribute("href")).toBe("/parent/sitters/s1");
    expect(container.textContent).not.toMatch(/₹|per hour|\/hour/);
    expect(calls[0]!.path).toBe("/parent/sitters?plan=pause&sort=distance");
  });

  test("filters become the search", async () => {
    const calls = mockApi({ "GET /parent/sitters": () => jsonResponse([]) });
    renderAt("/parent/sitters");
    expect(await screen.findByText(/No sitters match yet/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Plan"), { target: { value: "unwind" } });
    fireEvent.change(screen.getByLabelText(/Day/), { target: { value: "2026-11-10" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "18" } });
    fireEvent.change(screen.getByLabelText("Until"), { target: { value: "21" } });
    fireEvent.change(screen.getByLabelText(/Speaks/), { target: { value: "Kannada" } });
    fireEvent.change(screen.getByLabelText("Experience"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Rating"), { target: { value: "4.5" } });
    fireEvent.click(screen.getByLabelText("First-aid certified only"));
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "rating" } });
    fireEvent.click(screen.getByRole("button", { name: /Show sitters/ }));

    await waitFor(() => expect(calls).toHaveLength(2));
    const params = new URLSearchParams(calls[1]!.path.split("?")[1]);
    expect(Object.fromEntries(params)).toEqual({
      plan: "unwind",
      sort: "rating",
      starts_at: "2026-11-10T12:30:00.000Z",
      ends_at: "2026-11-10T15:30:00.000Z",
      language: "Kannada",
      min_years: "3",
      min_rating: "4.5",
      first_aid: "true",
    });
  });

  test("an end time before the start is caught before searching", async () => {
    const calls = mockApi({ "GET /parent/sitters": () => jsonResponse([]) });
    renderAt("/parent/sitters");
    await screen.findByText(/No sitters match yet/);
    fireEvent.change(screen.getByLabelText(/Day/), { target: { value: "2026-11-10" } });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "20" } });
    fireEvent.change(screen.getByLabelText("Until"), { target: { value: "19" } });
    fireEvent.click(screen.getByRole("button", { name: /Show sitters/ }));
    expect(screen.getByText("The end time must be after the start time.")).toBeTruthy();
    expect(calls).toHaveLength(1);
  });

  test("a parent who hasn't finished their profile is sent to finish it", async () => {
    mockApi({ "GET /parent/sitters": () => error("profile_unfinished", "Please finish your profile", 409) });
    renderAt("/parent/sitters");
    expect(await screen.findByText(/Finish your profile first/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Finish your profile/ }).getAttribute("href")).toBe("/parent");
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
    bio: "I love storytime.",
    plan: "pause",
    free_times: [{ starts_at: "2026-11-10T03:30:00Z", ends_at: "2026-11-10T07:30:00Z" }],
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

  test("a sitter who isn't available says so", async () => {
    mockApi({ "GET /parent/sitters/s9": () => error("not_found", "That sitter isn't available", 404) });
    renderAt("/parent/sitters/s9");
    expect(await screen.findByText("This sitter isn't available right now.")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Find a sitter/ })).toBeTruthy();
  });
});
