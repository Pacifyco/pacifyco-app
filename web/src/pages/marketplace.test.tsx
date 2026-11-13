import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { ageRange } from "../lib/sitterLists";
import { dayLabel, hourLabel, hoursLabel, kolkataTime, shortHour, todayInKolkata } from "../lib/times";
import { jsonResponse } from "../test/renderApp";
import { AvailabilityPage, addRange } from "./AvailabilityPage";
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

describe("week and day labels", () => {
  test("short hours and days read naturally", () => {
    expect(shortHour(9)).toBe("9 am");
    expect(shortHour(12)).toBe("12 pm");
    expect(shortHour(0)).toBe("12 am");
    expect(shortHour(24)).toBe("12 am");
    expect(hoursLabel(18, 22)).toBe("6 pm – 10 pm");
    expect(dayLabel("2026-11-15")).toBe("Sun 15 Nov");
  });
});

describe("a sitter's weekly availability", () => {
  const SAVED = {
    week: [
      { weekday: 0, start_hour: 9, end_hour: 13 },
      { weekday: 5, start_hour: 18, end_hour: 22 },
    ],
    days_off: ["2026-11-15"],
  };

  test("shows her week, one row per day, and her days off", async () => {
    mockApi({ "GET /sitter/availability": () => jsonResponse(SAVED) });
    renderAt("/sitter/availability");
    expect(await screen.findByRole("checkbox", { name: "Free on Mondays" })).toHaveProperty("checked", true);
    expect(screen.getByRole("checkbox", { name: "Free on Tuesdays" })).toHaveProperty("checked", false);
    expect(screen.getByLabelText("Monday from")).toHaveProperty("value", "9");
    expect(screen.getByLabelText("Saturday until")).toHaveProperty("value", "22");
    expect(screen.getAllByText("Not free")).toHaveLength(5);
    expect(within(screen.getByRole("list", { name: "Your days off" })).getByText("Sun 15 Nov")).toBeTruthy();
    // Nothing changed yet, so there's nothing to save.
    expect(screen.getByRole("button", { name: "Save my week" })).toHaveProperty("disabled", true);
  });

  test("a quick fill sets Monday to Friday on an empty week, and saving sends the whole week", async () => {
    const calls = mockApi({
      "GET /sitter/availability": () => jsonResponse({ week: [], days_off: [] }),
      "PUT /sitter/availability/week": (body) =>
        jsonResponse({ week: (body as { hours: unknown[] }).hours, days_off: [] }),
    });
    renderAt("/sitter/availability");
    fireEvent.click(await screen.findByRole("button", { name: "Evenings" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Free on Saturdays" })); // adds 9 am - 1 pm
    fireEvent.click(screen.getByRole("button", { name: "Add a time on Saturday" }));
    fireEvent.click(screen.getByRole("button", { name: "Save my week" }));

    await waitFor(() => expect(calls.some((call) => call.method === "PUT")).toBe(true));
    const put = calls.find((call) => call.method === "PUT")!;
    expect(put.body).toEqual({
      hours: [
        ...[0, 1, 2, 3, 4].map((weekday) => ({ weekday, start_hour: 18, end_hour: 22 })),
        { weekday: 5, start_hour: 9, end_hour: 13 },
        { weekday: 5, start_hour: 13, end_hour: 16 },
      ],
    });
    expect(await screen.findByText("Saved. It repeats every week until you change it.")).toBeTruthy();
  });

  test("a quick fill adds to the days already ticked, never wiping a time", async () => {
    // UX review 2026-11-13: "Afternoons" used to replace Monday's morning.
    mockApi({ "GET /sitter/availability": () => jsonResponse(SAVED) });
    renderAt("/sitter/availability");
    fireEvent.click(await screen.findByRole("button", { name: "Afternoons" }));
    // Monday 9-1 and the new 1-6 touch, so they join: 9 am to 6 pm.
    expect(screen.getByLabelText("Monday from")).toHaveProperty("value", "9");
    expect(screen.getByLabelText("Monday until")).toHaveProperty("value", "18");
    // Saturday keeps its evening and gains the afternoon before it: 1 pm to 10 pm.
    expect(screen.getByLabelText("Saturday from")).toHaveProperty("value", "13");
    expect(screen.getByLabelText("Saturday until")).toHaveProperty("value", "22");
    expect(screen.getByRole("checkbox", { name: "Free on Tuesdays" })).toHaveProperty("checked", false);
  });

  test("the quick fills are the four parts of the day parents filter by", async () => {
    mockApi({ "GET /sitter/availability": () => jsonResponse(SAVED) });
    renderAt("/sitter/availability");
    for (const name of ["Mornings", "Afternoons", "Evenings", "Nights"]) {
      expect(await screen.findByRole("button", { name })).toBeTruthy();
    }
    expect(addRange([{ start: 9, end: 13 }], { start: 18, end: 22 })).toEqual([
      { start: 9, end: 13 },
      { start: 18, end: 22 },
    ]);
    expect(addRange([{ start: 9, end: 14 }], { start: 13, end: 18 })).toEqual([{ start: 9, end: 18 }]);
  });

  test("unticking a day or removing its time clears it", async () => {
    mockApi({ "GET /sitter/availability": () => jsonResponse(SAVED) });
    renderAt("/sitter/availability");
    fireEvent.click(await screen.findByRole("button", { name: "Remove Saturday 6 pm – 10 pm" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Free on Mondays" }));
    expect(screen.getAllByText("Not free")).toHaveLength(7);
  });

  test("an end before the start is caught, and the API's reason is shown", async () => {
    mockApi({
      "GET /sitter/availability": () => jsonResponse(SAVED),
      "PUT /sitter/availability/week": () => error("hours_overlap", "Two times on the same day overlap", 422),
    });
    renderAt("/sitter/availability");
    fireEvent.change(await screen.findByLabelText("Monday until"), { target: { value: "8" } });
    fireEvent.click(screen.getByRole("button", { name: "Save my week" }));
    expect(screen.getByText("Each time must end after it starts.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Monday until"), { target: { value: "14" } });
    fireEvent.click(screen.getByRole("button", { name: "Save my week" }));
    expect(await screen.findByText("Two times on the same day overlap")).toBeTruthy();
  });

  test("days off are marked and removed", async () => {
    const calls = mockApi({
      "GET /sitter/availability": () => jsonResponse(SAVED),
      "POST /sitter/availability/days-off": () => jsonResponse({ ...SAVED, days_off: ["2026-11-15", "2026-11-20"] }, 201),
      "DELETE /sitter/availability/days-off/2026-11-15": () => new Response(null, { status: 204 }),
    });
    renderAt("/sitter/availability");
    fireEvent.click(await screen.findByRole("button", { name: "Mark day off" }));
    expect(screen.getByText("Please choose a day.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Day"), { target: { value: "2026-11-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Mark day off" }));
    expect(await screen.findByText("Fri 20 Nov")).toBeTruthy();
    expect(calls).toContainEqual({ method: "POST", path: "/sitter/availability/days-off", body: { day: "2026-11-20" } });

    fireEvent.click(screen.getByRole("button", { name: "Remove day off Sun 15 Nov" }));
    await waitFor(() =>
      expect(calls).toContainEqual({ method: "DELETE", path: "/sitter/availability/days-off/2026-11-15", body: null }),
    );
  });
});

describe("finding a sitter", () => {
  const LAKSHMI = {
    id: "s1",
    full_name: "Lakshmi Nair",
    years_experience: 4,
    age_groups: ["Toddler", "Preschool"],
    languages: ["English", "Kannada"],
    first_aid: true,
    avg_rating: null,
    review_count: 0,
    distance_km: 2.37,
    photo_url: "https://storage.example/photo/s1?token=x",
    plan: "pause",
  };
  const FINISHED = { items: [], finished: true };

  test("each card shows the plan the sitter works, as a small label with no price", async () => {
    mockApi({
      "GET /parent/checklist": () => jsonResponse(FINISHED),
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

  test("lists every live sitter with no prices, as the parent's home, on a short card", async () => {
    const calls = mockApi({
      "GET /parent/checklist": () => jsonResponse(FINISHED),
      "GET /parent/sitters": () => jsonResponse([LAKSHMI]),
    });
    const { container } = renderAt("/parent/sitters");
    const card = within((await screen.findByRole("heading", { name: "Lakshmi Nair" })).closest("article")!);
    expect(card.getByText("4 yrs · 2.4 km · Ages 1½–5")).toBeTruthy();
    expect(card.getByRole("img", { name: "Lakshmi Nair" }).getAttribute("src")).toBe(
      "https://storage.example/photo/s1?token=x",
    );
    expect(card.getByText("First-aid certified")).toBeTruthy();
    expect(card.queryByText("Psychology screening passed")).toBeNull(); // placeholder questions for now
    expect(card.queryByText("Kannada")).toBeNull(); // the card stays short (UX review 2026-11-13)
    expect(card.getByRole("link", { name: "See Lakshmi's profile" }).getAttribute("href")).toBe("/parent/sitters/s1");
    expect(container.textContent).not.toMatch(/₹|per hour|\/hour/);
    expect(calls.find((call) => call.path.startsWith("/parent/sitters"))!.path).toBe("/parent/sitters?sort=distance");
    expect(screen.getByText("1 sitter")).toBeTruthy(); // a live count
    // It's the parent's home page, so there's no back link to a home.
    expect(screen.getByRole("heading", { level: 1, name: "Find a sitter" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Home" })).toBeNull();
  });

  test("filters start with when, and every filter applies straight away", async () => {
    const calls = mockApi({
      "GET /parent/checklist": () => jsonResponse(FINISHED),
      "GET /parent/sitters": () => jsonResponse([LAKSHMI]),
    });
    renderAt("/parent/sitters");
    await screen.findByRole("heading", { name: "Lakshmi Nair" });
    expect(screen.getByRole("group", { name: "When?" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Evening" })); // no day yet: today
    fireEvent.click(screen.getByRole("button", { name: "Kannada" }));
    fireEvent.click(screen.getByRole("button", { name: "First aid" }));
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "rating" } });

    await waitFor(() => expect(calls.at(-1)!.path).toContain("sort=rating"));
    const params = new URLSearchParams(calls.at(-1)!.path.split("?")[1]);
    expect(Object.fromEntries(params)).toEqual({
      sort: "rating",
      day: todayInKolkata(),
      part: "evening",
      language: "Kannada",
      first_aid: "true",
    });
    expect(screen.getByRole("button", { name: "Evening" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("1 sitter free today evening")).toBeTruthy();
  });

  test("filters are read from the address, so Back and refresh keep them", async () => {
    const calls = mockApi({
      "GET /parent/checklist": () => jsonResponse(FINISHED),
      "GET /parent/sitters": () => jsonResponse([LAKSHMI]),
    });
    renderAt("/parent/sitters?day=2026-11-20&time=morning&firstaid=1");
    await screen.findByRole("heading", { name: "Lakshmi Nair" });
    const params = new URLSearchParams(calls.find((call) => call.path.startsWith("/parent/sitters"))!.path.split("?")[1]);
    expect(Object.fromEntries(params)).toEqual({ sort: "distance", day: "2026-11-20", part: "morning", first_aid: "true" });
    expect(screen.getByRole("button", { name: "First aid" }).getAttribute("aria-pressed")).toBe("true");
  });

  test("an empty result offers a way out, with how many each would show", async () => {
    mockApi({
      "GET /parent/checklist": () => jsonResponse(FINISHED),
      "GET /parent/sitters?sort=distance&first_aid=true": () => jsonResponse([]),
      "GET /parent/sitters?sort=distance": () => jsonResponse([LAKSHMI, { ...LAKSHMI, id: "s2" }]),
    });
    renderAt("/parent/sitters?firstaid=1");
    expect(await screen.findByText("No sitters match all of these.")).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Remove First aid · 2 sitters" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear all filters" }));
    expect(await screen.findByText("2 sitters")).toBeTruthy();
  });

  test("until the profile is finished, there are no filters, just what's left", async () => {
    mockApi({
      "GET /parent/checklist": () =>
        jsonResponse({
          items: [
            { key: "consent", status: "done" },
            { key: "details", status: "done" },
            { key: "children", status: "to_do" },
            { key: "emergency_contacts", status: "to_do" },
          ],
          finished: false,
        }),
    });
    renderAt("/parent/sitters");
    expect(await screen.findByText(/Finish your profile first.*2 of 4 done/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /Finish your profile/ }).getAttribute("href")).toBe("/parent/profile");
    expect(screen.queryByRole("group", { name: "When?" })).toBeNull();
  });

  test("ages read as one range", () => {
    expect(ageRange(["Toddler", "Preschool"])).toBe("Ages 1½–5");
    expect(ageRange(["School age"])).toBe("Ages 6–12");
    expect(ageRange(["2 3 4"])).toBeNull(); // old free text isn't shown
  });
});

describe("a sitter's profile page", () => {
  const DETAIL = {
    id: "s1",
    full_name: "Lakshmi Nair",
    years_experience: 4,
    age_groups: ["Preschool"],
    languages: ["English", "Tamil"],
    first_aid: false,
    avg_rating: 4.8,
    review_count: 12,
    distance_km: 0.4,
    photo_url: null,
    bio: "I love storytime.",
    plan: "pause",
    week: [
      { weekday: 0, start_hour: 9, end_hour: 13 },
      { weekday: 0, start_hour: 18, end_hour: 22 },
      { weekday: 5, start_hour: 10, end_hour: 14 },
    ],
    days_off: ["2026-11-15"],
    reference: null,
    joined_at: "2026-11-02T10:00:00Z",
  };
  const CHILDREN = () => jsonResponse([{ id: "c1", name: "Diya", date_of_birth: "2022-05-01" }]);

  test("shows who she is, when she's free and the 1-hour nudge, with no price", async () => {
    mockApi({ "GET /parent/sitters/s1": () => jsonResponse(DETAIL), "GET /parent/children": CHILDREN });
    const { container } = renderAt("/parent/sitters/s1");
    expect(await screen.findByRole("heading", { level: 1, name: "Lakshmi Nair" })).toBeTruthy();
    expect(screen.getByText("4 years' experience · under 1 km away · Joined Nov 2026")).toBeTruthy();
    expect(screen.queryByText("New to Pacify")).toBeNull();
    expect(screen.getByText("I love storytime.")).toBeTruthy();
    expect(screen.getByText("Comfortable with ages 3–5")).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "Languages" })).getByText("Tamil")).toBeTruthy();
    expect(await screen.findByText(/Suits Diya \(4\)/)).toBeTruthy();
    expect(screen.getByText(/works the Pause plan: one child, until 6 pm/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "When Lakshmi is usually free" })).toBeTruthy();
    // A week grid: every day, with "Not available" where she isn't free.
    const monday = screen.getByRole("rowheader", { name: "Mon" }).closest("tr")!;
    expect(within(monday).getAllByText("Free")).toHaveLength(2); // morning and evening
    const tuesday = screen.getByRole("rowheader", { name: "Tue" }).closest("tr")!;
    expect(within(tuesday).getByText("Not available")).toBeTruthy();
    expect(screen.getByText("Not free on Sun 15 Nov.")).toBeTruthy();
    expect(screen.getByText(/Start with a 1-hour booking while you're at home/)).toBeTruthy();
    expect(screen.queryByText("First-aid certified")).toBeNull();
    expect(container.textContent).not.toMatch(/₹|per hour|\/hour/);
  });

  test("each check opens to say what Pacify checked", async () => {
    mockApi({ "GET /parent/sitters/s1": () => jsonResponse(DETAIL), "GET /parent/children": CHILDREN });
    renderAt("/parent/sitters/s1");
    const badge = (await screen.findByText("ID & police verified")).closest("details")!;
    expect(within(badge).getByText(/police clearance certificate/)).toBeTruthy();
  });

  test("a Recharge sitter's shared reference is shown, never with a phone number", async () => {
    const reference = { name: "Asha Rao", relationship: "Former employer" };
    mockApi({
      "GET /parent/sitters/s1": () => jsonResponse({ ...DETAIL, plan: "recharge", reference }),
      "GET /parent/children": CHILDREN,
    });
    const { container } = renderAt("/parent/sitters/s1");
    expect(await screen.findByRole("heading", { name: "A reference for Lakshmi" })).toBeTruthy();
    expect(screen.getByText("Asha Rao · Former employer")).toBeTruthy();
    expect(container.querySelector('a[href^="tel:"]')).toBeNull();
  });

  test("no reference card without a shared reference", async () => {
    mockApi({ "GET /parent/sitters/s1": () => jsonResponse(DETAIL), "GET /parent/children": CHILDREN });
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
