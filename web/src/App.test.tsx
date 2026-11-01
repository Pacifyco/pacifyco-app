import { screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { jsonResponse, renderApp } from "./test/renderApp";

describe("routes", () => {
  test.each([
    ["/", "A little help for you. A little more fun for them."],
    ["/parent", "Time for you."],
    ["/sitter", "Your work with Pacify."],
    ["/admin", "Admin"],
    ["/no-such-page", "We couldn't find that page."],
  ])("%s shows its page", async (path, heading) => {
    renderApp(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeTruthy();
  });

  test("the layout links home and has a main landmark", async () => {
    renderApp("/parent");
    expect(await screen.findByRole("link", { name: "Pacify home" })).toBeTruthy();
    expect(screen.getByRole("main")).toBeTruthy();
  });
});

describe("environment footer", () => {
  test("shows the API as connected when /health answers", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: "ok", environment: "local" }));
    renderApp();
    expect(await screen.findByText(/API: connected/)).toBeTruthy();
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("http://localhost:8000/health");
  });

  test("shows the API as not reachable when /health fails", async () => {
    renderApp();
    expect(await screen.findByText(/API: not reachable/)).toBeTruthy();
  });
});
