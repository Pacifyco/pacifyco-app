import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { renderApp } from "../test/renderApp";
import { MemoryRouter } from "react-router";
import { describe, expect, test } from "vitest";
import { sections } from "../lib/markdown";
import { NotFoundPage } from "./ErrorPages";
import { PrivacyPolicyPage } from "./LegalPages";

// UX review 2026-11-13: the public pages.

function renderPage(page: React.ReactNode) {
  return render(<MemoryRouter>{page}</MemoryRouter>);
}

describe("legal pages", () => {
  test("have a real H1 and a contents list that links to each section", () => {
    renderPage(<PrivacyPolicyPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Privacy policy" })).toBeTruthy();
    // Desktop: a sticky contents list. Phones: "Jump to section".
    const contents = screen.getByRole("navigation", { name: "Contents" });
    const link = within(contents).getByRole("link", { name: "Who we are" });
    expect(link.getAttribute("href")).toBe("#who-we-are");
    expect(document.getElementById("who-we-are")!.textContent).toBe("Who we are");
    expect(screen.getByText("Jump to section")).toBeTruthy();
  });

  test("a bold first line is shown as the title, without changing the text", () => {
    const body = "**Pacifyco Family Terms of Use**\n\n## **At a glance**\n\nText.\n\n## 1. Who\n\nMore.\n\n## 2. What\n\nEnd.";
    expect(sections(body)).toEqual([
      { id: "at-a-glance", text: "At a glance" },
      { id: "1-who", text: "1. Who" },
      { id: "2-what", text: "2. What" },
    ]);
  });
});

describe("the privacy policy's Back button", () => {
  test("goes back to the page the footer link was pressed on", async () => {
    const { router } = renderApp("/terms/sitter");
    fireEvent.click(await screen.findByRole("link", { name: "Privacy policy" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/privacy"));
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/terms/sitter"));
  });

  test("opened directly, it leads home", async () => {
    renderApp("/privacy");
    expect((await screen.findByRole("link", { name: "Back" })).getAttribute("href")).toBe("/");
  });
});

describe("the pinned header", () => {
  function scrollTo(y: number) {
    act(() => {
      Object.defineProperty(window, "scrollY", { value: y, configurable: true });
      window.dispatchEvent(new Event("scroll"));
    });
  }

  test("stays at the top, hides while scrolling down, and comes back with Back when scrolling up", async () => {
    const { router } = renderApp("/terms/sitter");
    fireEvent.click(await screen.findByRole("link", { name: "Privacy policy" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/privacy"));
    const header = screen.getByRole("banner");
    expect(header.className).toContain("sticky");
    // At the top: only the page's own Back, not a second one in the header.
    expect(within(header).queryByRole("button", { name: "Back" })).toBeNull();

    scrollTo(400); // down: the header slides away
    expect(header.className).toContain("-translate-y-full");
    scrollTo(300); // up: it comes back, with Back
    expect(header.className).not.toContain("-translate-y-full");
    fireEvent.click(within(header).getByRole("button", { name: "Back" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/terms/sitter"));
    scrollTo(0);
  });
});

describe("the 404 page", () => {
  test("offers the home page, sign-in and help", () => {
    renderPage(<NotFoundPage />);
    expect(screen.getByRole("link", { name: "Go to the home page" }).getAttribute("href")).toBe("/");
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/?signin");
    expect(screen.getByRole("link", { name: "Get help" }).getAttribute("href")).toBe("mailto:founders@pacifyco.in");
  });
});
