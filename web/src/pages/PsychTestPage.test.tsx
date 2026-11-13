import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { PsychTestPage } from "./PsychTestPage";

// Wrapped in a MemoryRouter because the page links back to the application page.
function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PsychTestPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const QUESTIONS = [
  { id: "q1", order_index: 1, kind: "multiple_choice", prompt: "Pick one", options: ["A", "B"] },
  { id: "q2", order_index: 2, kind: "short_answer", prompt: "Explain yourself", options: null },
];

type Call = { url: string; init?: RequestInit };

function mockApi(attempt: { status: string; submitted_at: string | null; answers: Record<string, string>; retake_allowed?: boolean } | null) {
  const calls: Call[] = [];
  let currentAttempt = attempt;
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    calls.push({ url, init });
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    if (path === "/sitter/psych-test" && (!init || !init.method)) {
      return Promise.resolve(
        jsonResponse({ test_id: "test-1", is_placeholder: true, questions: QUESTIONS, attempt: currentAttempt }),
      );
    }
    if (path === "/sitter/psych-test/answers" && init?.method === "PUT") {
      const body = JSON.parse(init.body as string) as { answers: { question_id: string; answer_text: string }[] };
      currentAttempt = {
        status: "in_progress",
        submitted_at: null,
        answers: Object.fromEntries(body.answers.map((a) => [a.question_id, a.answer_text])),
      };
      return Promise.resolve(jsonResponse(currentAttempt));
    }
    if (path === "/sitter/psych-test/submit" && init?.method === "POST") {
      currentAttempt = { ...currentAttempt!, status: "submitted", submitted_at: "2026-11-04T10:00:00Z" };
      return Promise.resolve(jsonResponse(currentAttempt));
    }
    return Promise.reject(new Error(`unexpected request: ${init?.method ?? "GET"} ${path}`));
  }) as typeof fetch);
  return calls;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("the psychology screening page", () => {
  test("a screening statement is rated from 1 (least relevant) to 5 (most relevant)", async () => {
    // Reuben's screening questions (2026-11-13).
    const scale = [{ id: "s1", order_index: 1, kind: "scale", prompt: "I stay calm even when work piles up suddenly.", options: null }];
    vi.mocked(fetch).mockImplementation(((url: string) =>
      Promise.resolve(
        String(url).endsWith("/sitter/psych-test")
          ? jsonResponse({ test_id: "t", is_placeholder: false, questions: scale, attempt: null })
          : jsonResponse({}, 404),
      )) as typeof fetch);
    renderPage();
    const group = await screen.findByRole("group", { name: "I stay calm even when work piles up suddenly." });
    expect(group).toBeTruthy();
    for (const number of ["1", "2", "3", "4", "5"]) expect(screen.getByRole("radio", { name: number })).toBeTruthy();
    expect(screen.getByText("1 = least relevant")).toBeTruthy();
    expect(screen.getByText("5 = most relevant")).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: "4" }));
    expect((screen.getByRole("radio", { name: "4" }) as HTMLInputElement).checked).toBe(true);
  });

  test("shows one question at a time, starting with the first", async () => {
    mockApi(null);
    renderPage();
    expect(await screen.findByText("Pick one")).toBeTruthy();
    expect(screen.getByText("Question 1 of 2")).toBeTruthy();
    expect(screen.getByLabelText("A")).toBeTruthy();
    expect(screen.getByLabelText("B")).toBeTruthy();
    expect(screen.queryByLabelText("Explain yourself")).toBeNull();
    expect(screen.queryByRole("button", { name: "Submit" })).toBeNull();
  });

  test("won't move on until the question is answered", async () => {
    mockApi(null);
    renderPage();
    await screen.findByText("Pick one");

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Please answer this question to continue.")).toBeTruthy();
    expect(screen.getByText("Question 1 of 2")).toBeTruthy();
  });

  test("Back returns to the question before, keeping its answer", async () => {
    mockApi(null);
    renderPage();
    await screen.findByText("Pick one");
    fireEvent.click(screen.getByLabelText("B"));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByLabelText("Explain yourself")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "← Back" }));
    expect(await screen.findByText("Question 1 of 2")).toBeTruthy();
    expect((screen.getByLabelText("B") as HTMLInputElement).checked).toBe(true);
  });

  test("submitting sends every answer, then confirms the application is submitted", async () => {
    const calls = mockApi(null);
    renderPage();
    await screen.findByText("Pick one");

    fireEvent.click(screen.getByLabelText("A"));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.change(await screen.findByLabelText("Explain yourself"), { target: { value: "Because I care." } });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() =>
      expect(calls.some((call) => call.url.endsWith("/sitter/psych-test/submit") && call.init?.method === "POST")).toBe(
        true,
      ),
    );
    const put = calls.find((call) => call.url.endsWith("/sitter/psych-test/answers"))!;
    expect(JSON.parse(put.init!.body as string)).toEqual({
      answers: [
        { question_id: "q1", answer_text: "A" },
        { question_id: "q2", answer_text: "Because I care." },
      ],
    });
    expect(await screen.findByText("Your application is submitted.")).toBeTruthy();
    expect(screen.queryByText("Pick one")).toBeNull();
    // Only the confirmation: no heading, intro or links around it (Reuben, 2026-11-13).
    expect(screen.queryByRole("heading", { name: "Psychology screening" })).toBeNull();
    expect(screen.queryByText(/A few questions so we can get to know/)).toBeNull();
    expect(screen.queryByRole("link", { name: "Back to your application" })).toBeNull();
  });

  test("an already-submitted attempt shows the awaiting-review state, not the form", async () => {
    mockApi({ status: "submitted", submitted_at: "2026-11-04T10:00:00Z", answers: { q1: "A", q2: "Because." } });
    renderPage();
    expect(await screen.findByText(/An admin will look over your answers/)).toBeTruthy();
    expect(screen.queryByText("Pick one")).toBeNull();
  });

  test("a passed attempt shows the passed state", async () => {
    mockApi({ status: "passed", submitted_at: "2026-11-04T10:00:00Z", answers: { q1: "A", q2: "Because." } });
    renderPage();
    expect(await screen.findByText("You've passed the psychology screening.")).toBeTruthy();
  });

  test("a failed attempt waits for Pacifyco to allow a retake", async () => {
    mockApi({
      status: "failed",
      submitted_at: "2026-11-04T10:00:00Z",
      answers: { q1: "A", q2: "Because." },
      retake_allowed: false,
    });
    renderPage();
    expect(await screen.findByText(/Pacifyco will be in touch about whether you can take the screening again/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });

  test("once Pacifyco allows it, a failed attempt offers to try again with a fresh form", async () => {
    mockApi({
      status: "failed",
      submitted_at: "2026-11-04T10:00:00Z",
      answers: { q1: "A", q2: "Because." },
      retake_allowed: true,
    });
    renderPage();
    expect(await screen.findByText("You didn't pass this time, and Pacifyco has said you can try again.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Pick one")).toBeTruthy();
    expect((screen.getByLabelText("A") as HTMLInputElement).checked).toBe(false);
  });

  test("an in-progress attempt prefills its saved answers", async () => {
    mockApi({ status: "in_progress", submitted_at: null, answers: { q1: "B", q2: "Half-finished." } });
    renderPage();
    await screen.findByText("Pick one");
    expect((screen.getByLabelText("B") as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(((await screen.findByLabelText("Explain yourself")) as HTMLTextAreaElement).value).toBe("Half-finished.");
  });
});
