import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../test/renderApp";
import { SitterReviewsPage, type SitterReviews } from "./SitterReviewsPage";

// Her reviews (CLAUDE.md 6.11): families' reviews as parents see them, and, if her ratings are being
// reviewed, the reason and her response.

const DATA: SitterReviews = {
  avg_rating: 4.5,
  review_count: 2,
  reviews: [
    { rating: 5, body: "Diya loved her.", author_first_name: "Priya", created_at: "2026-11-20T10:00:00Z" },
    { rating: 4, body: null, author_first_name: "Arjun", created_at: "2026-10-03T10:00:00Z" },
  ],
  flag: null,
};

const FLAG = {
  id: "f1",
  reason: "Two families said you were on your phone.",
  told_at: "2026-11-21T10:00:00Z",
  response: null,
  responded_at: null,
  respond_by: "2030-01-05T22:00:00Z",
};

function renderWith(data: SitterReviews, after?: SitterReviews) {
  const posted: { url: string; body: unknown }[] = [];
  vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      posted.push({ url, body: JSON.parse(init.body as string) as unknown });
      return Promise.resolve(jsonResponse(after));
    }
    return Promise.resolve(jsonResponse(data));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <SitterReviewsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return posted;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("Your reviews", () => {
  test("her average, count and each family's review", async () => {
    renderWith(DATA);
    expect(await screen.findByText("4.5 · 2 reviews")).toBeTruthy();
    const list = within(screen.getByRole("list", { name: "Families' reviews" }));
    expect(list.getByText("Diya loved her.")).toBeTruthy();
    expect(list.getByText("Arjun · Oct 2026")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Your ratings are being reviewed" })).toBeNull();
  });

  test("nothing yet", async () => {
    renderWith({ avg_rating: null, review_count: 0, reviews: [], flag: null });
    expect(await screen.findByText("No reviews yet. Families can review you after each booking.")).toBeTruthy();
  });

  test("told why her ratings are being reviewed, she responds", async () => {
    const answered = {
      ...DATA,
      flag: { ...FLAG, response: "The parent was calling me.", responded_at: "2026-11-22T10:00:00Z" },
    };
    const posted = renderWith({ ...DATA, flag: FLAG }, answered);
    const card = within(await screen.findByRole("region", { name: "Your ratings are being reviewed" }));
    expect(card.getByText("Two families said you were on your phone.")).toBeTruthy();
    expect(card.getByText("Please respond by Sun, 6 Jan, 3:30 am.")).toBeTruthy();
    fireEvent.click(card.getByRole("button", { name: "Send your response" }));
    expect(await card.findByText("Write your response.")).toBeTruthy();
    fireEvent.change(card.getByLabelText(/Your response/), { target: { value: " The parent was calling me. " } });
    fireEvent.click(card.getByRole("button", { name: "Send your response" }));
    expect(await card.findByText("We'll tell you what we decide.")).toBeTruthy();
    expect(card.getByText("The parent was calling me.")).toBeTruthy();
    expect(card.queryByRole("button", { name: "Send your response" })).toBeNull();
    expect(posted).toEqual([
      { url: expect.stringMatching(/\/sitter\/rating-flags\/f1\/respond$/), body: { response: "The parent was calling me." } },
    ]);
  });
});
