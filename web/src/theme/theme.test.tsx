import { act, fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { renderApp } from "../test/renderApp";
import { setSystemDark } from "../test/setup";
import { THEME_STORAGE_KEY, getStoredPreference, resolveTheme } from "./theme";

const html = document.documentElement;

describe("theme rules", () => {
  test("system preference follows the OS", () => {
    expect(resolveTheme("system")).toBe("light");
    setSystemDark(true);
    expect(resolveTheme("system")).toBe("dark");
  });

  test("a manual choice beats the OS", () => {
    setSystemDark(true);
    expect(resolveTheme("light")).toBe("light");
  });

  test("unknown stored values fall back to system", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "purple");
    expect(getStoredPreference()).toBe("system");
  });
});

describe("theme toggle (sun and moon, no System button)", () => {
  const pressed = (name: string) => screen.getByRole("button", { name }).getAttribute("aria-pressed");

  test("only light and dark are offered, shown as a sun and a moon", async () => {
    renderApp();
    const group = await screen.findByRole("group", { name: "Theme" });
    expect(within(group).getAllByRole("button")).toHaveLength(2);
    expect(within(group).getByRole("button", { name: "Light theme" }).textContent).toBe("☀️");
    expect(within(group).getByRole("button", { name: "Dark theme" }).textContent).toBe("🌙");
    expect(screen.queryByRole("button", { name: /System/ })).toBeNull();
  });

  test("follows the OS until someone picks, showing the matching option as on", async () => {
    renderApp();
    await screen.findByRole("group", { name: "Theme" });
    expect(html.dataset.theme).toBe("light");
    expect(pressed("Light theme")).toBe("true");
    expect(pressed("Dark theme")).toBe("false");

    act(() => setSystemDark(true));
    expect(html.dataset.theme).toBe("dark");
    expect(pressed("Dark theme")).toBe("true");
  });

  test("choosing dark applies it, remembers it and ignores the OS", async () => {
    renderApp();
    fireEvent.click(await screen.findByRole("button", { name: "Dark theme" }));

    expect(html.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(pressed("Dark theme")).toBe("true");

    act(() => setSystemDark(false));
    expect(html.dataset.theme).toBe("dark");
  });

  test("switching back to light works the same way", async () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    renderApp();
    fireEvent.click(await screen.findByRole("button", { name: "Light theme" }));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(html.dataset.theme).toBe("light");
  });

  test("a stored choice is used on the next visit", async () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    renderApp();
    await screen.findByRole("group", { name: "Theme" });
    expect(html.dataset.theme).toBe("dark");
  });
});
