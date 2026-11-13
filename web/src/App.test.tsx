import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { renderApp } from "./test/renderApp";

describe("routes", () => {
  test.each([
    ["/", "A little help for you. A little more fun for them."],
    ["/no-such-page", "We couldn't find that page."],
  ])("%s shows its page", async (path, heading) => {
    renderApp(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeTruthy();
  });

  test("the home page opens the sign-in box in place of its button; there's no sign-in page", async () => {
    const { router } = renderApp("/");
    fireEvent.click(await screen.findByRole("button", { name: /Sign in or join/ }));
    expect(await screen.findByRole("heading", { name: "Sign in to Pacify." })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Sign in or join/ })).toBeNull();
    expect(router.state.location.pathname).toBe("/");
    expect(router.state.location.search).toBe("?signin=");
  });

  test("the old /sign-in address lands on the home page with the box open", async () => {
    const { router } = renderApp("/sign-in");
    expect(await screen.findByRole("heading", { name: "Sign in to Pacify." })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: "A little help for you. A little more fun for them." })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/");
  });

  test.each(["/parent", "/sitter", "/admin"])("%s needs sign-in", async (path) => {
    const { router } = renderApp(path);
    expect(await screen.findByRole("heading", { name: "Sign in to Pacify." })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/");
  });

  test("the layout links home and has a main landmark", async () => {
    renderApp("/");
    expect(await screen.findByRole("link", { name: "Pacify home" })).toBeTruthy();
    expect(screen.getByRole("main")).toBeTruthy();
  });
});

test("without Supabase settings, sign-in says it isn't set up", async () => {
  renderApp("/sign-in");
  expect(await screen.findByText("Sign-in isn't set up in this environment yet.")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
});

test("no environment line at the bottom of the page (Reuben, 2026-11-13)", async () => {
  renderApp();
  await screen.findByRole("navigation", { name: "Legal" });
  expect(screen.queryByText(/Environment:/)).toBeNull();
});
