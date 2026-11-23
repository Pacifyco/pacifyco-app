import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../../test/renderApp";
import { PeoplePage, type PersonRow } from "./PeoplePage";

// Finding a parent or sitter (phase 10): by name, email or phone, with role and account filters.

const PEOPLE: PersonRow[] = [
  {
    id: "s1",
    role: "sitter",
    full_name: "Lakshmi Nair",
    email: "lakshmi@example.com",
    phone: "+919876543210",
    status: "suspended",
    created_at: "2030-01-05T04:30:00Z",
  },
  {
    id: "p1",
    role: "parent",
    full_name: "Priya Rao",
    email: "priya@example.com",
    phone: null,
    status: "active",
    created_at: "2030-01-04T04:30:00Z",
  },
];

function renderPage() {
  const urls: string[] = [];
  vi.mocked(fetch).mockImplementation(((url: string) => {
    urls.push(url);
    return Promise.resolve(jsonResponse(url.includes("q=") ? [] : PEOPLE));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/admin/people"]}>
        <PeoplePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return urls;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("People", () => {
  test("each person links to their page, with their account's status", async () => {
    renderPage();
    const sitter = await screen.findByRole("link", { name: /Lakshmi Nair/ });
    expect(sitter.getAttribute("href")).toBe("/admin/sitters/s1");
    expect(sitter.textContent).toContain("Suspended");
    expect(screen.getByRole("link", { name: /Priya Rao/ }).getAttribute("href")).toBe("/admin/parents/p1");
  });

  test("searching and filtering ask the API", async () => {
    const urls = renderPage();
    await screen.findByRole("link", { name: /Lakshmi Nair/ });
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "sitter" } });
    await waitFor(() => expect(urls.at(-1)).toMatch(/\/admin\/people\?role=sitter$/));
    fireEvent.change(screen.getByLabelText("Name, email or phone"), { target: { value: "nobody" } });
    expect(await screen.findByText("No one matches.")).toBeTruthy();
    expect(urls.at(-1)).toMatch(/\/admin\/people\?q=nobody&role=sitter$/);
  });
});
