import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { kolkataTime } from "../../lib/times";
import { jsonResponse } from "../../test/renderApp";
import { DocumentAccessLogPage, type DocumentView } from "./DocumentAccessLogPage";

// The document access log, for admins (phase 10): which admin opened whose document, and when.

const VIEW: DocumentView = {
  id: 1,
  at: kolkataTime("2030-01-07", 9),
  admin_name: "Asha Admin",
  admin_id: "a1",
  document_id: "d1",
  document_type: "birth_certificate",
  deleted: true,
  owner: { id: "p1", full_name: "Priya Rao", role: "parent" },
  child_name: "Asha",
};

function renderPage() {
  const urls: string[] = [];
  vi.mocked(fetch).mockImplementation(((url: string) => {
    if (url.includes("/admin/document-access-log")) urls.push(url);
    if (url.endsWith("/admin/admins")) return Promise.resolve(jsonResponse([{ id: "a1", full_name: "Asha Admin" }]));
    return Promise.resolve(jsonResponse({ views: url.includes("owner=") ? [] : [VIEW], more: false }));
  }) as unknown as typeof fetch);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/admin/document-access-log"]}>
        <DocumentAccessLogPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return urls;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("The document access log", () => {
  test("each view: the document, whose, who opened it and when", async () => {
    renderPage();
    const owner = await screen.findByRole("link", { name: "Priya Rao" });
    expect(owner.getAttribute("href")).toBe("/admin/parents/p1");
    expect(owner.closest("p")?.textContent).toBe("Birth certificate for Asha · Priya Rao");
    expect(screen.getByText("Opened by Asha Admin · Mon, 7 Jan, 9:00 am · File since deleted")).toBeTruthy();
  });

  test("filters ask the API", async () => {
    const urls = renderPage();
    await screen.findByRole("link", { name: "Priya Rao" });
    await screen.findByRole("option", { name: "Asha Admin" });
    fireEvent.change(screen.getByLabelText("Opened by"), { target: { value: "a1" } });
    await waitFor(() => expect(urls.at(-1)).toMatch(/\/admin\/document-access-log\?admin_id=a1&page=0$/));
    fireEvent.change(screen.getByLabelText("Document"), { target: { value: "police_certificate" } });
    await waitFor(() => expect(urls.at(-1)).toMatch(/admin_id=a1&document_type=police_certificate&page=0$/));
    fireEvent.change(screen.getByLabelText("Until"), { target: { value: "2030-01-31" } });
    await waitFor(() => expect(urls.at(-1)).toMatch(/on_to=2030-01-31&page=0$/));
    fireEvent.change(screen.getByLabelText("Whose document (their name)"), { target: { value: "nobody" } });
    expect(await screen.findByText("Nothing matches.")).toBeTruthy();
  });
});
