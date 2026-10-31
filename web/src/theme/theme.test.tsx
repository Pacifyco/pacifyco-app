import { act, fireEvent, screen } from "@testing-library/react";
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

describe("theme toggle", () => {
  test("follows the OS by default, including live changes", async () => {
    renderApp();
    await screen.findByRole("group", { name: "Theme" });
    expect(html.dataset.theme).toBe("light");
    expect(screen.getByRole("button", { name: "System" }).getAttribute("aria-pressed")).toBe("true");

    act(() => setSystemDark(true));
    expect(html.dataset.theme).toBe("dark");
  });

  test("choosing dark applies it, remembers it and ignores the OS", async () => {
    renderApp();
    fireEvent.click(await screen.findByRole("button", { name: "Dark" }));

    expect(html.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(screen.getByRole("button", { name: "Dark" }).getAttribute("aria-pressed")).toBe("true");

    act(() => setSystemDark(false));
    expect(html.dataset.theme).toBe("dark");
  });

  test("going back to system clears the stored choice", async () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    renderApp();
    fireEvent.click(await screen.findByRole("button", { name: "System" }));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(html.dataset.theme).toBe("light");
  });

  test("a stored choice is used on the next visit", async () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    renderApp();
    await screen.findByRole("group", { name: "Theme" });
    expect(html.dataset.theme).toBe("dark");
  });
});
