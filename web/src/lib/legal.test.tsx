import { screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import sitterTermsSource from "../content/sitter-terms-v1.1.md?raw";
import { renderApp } from "../test/renderApp";
import { fillSitterTerms } from "./legal";

// Fingerprint of the final Sitter Terms of Use v1.1 (CLAUDE.md 7: never change its wording). If this
// fails, the file was edited: undo the edit. A new version is a new file with a new fingerprint.
const SITTER_TERMS_SHA256 = "0b2796dde3e7de1f373cc20defa6c327dcfb68105fb5fd8024544f5c4bc67b41";

const VALUES = {
  llpin: "AAA-1234",
  address: "12 MG Road, Bengaluru 560001",
  grievanceName: "Priya Rao",
  grievanceEmail: "grievance@example.com",
  grievancePhone: "+91 90000 00001",
  emergencyLine: "+91 90000 00002",
  sitterTermsDate: "2026-11-15",
};
const EMPTY = Object.fromEntries(Object.keys(VALUES).map((key) => [key, ""])) as typeof VALUES;
// A placeholder as written in the terms: \[UPPER CASE\]
const PLACEHOLDER = /\\\[[A-Z ]+\\\]/;

describe("Sitter Terms of Use v1.1", () => {
  test("wording is unchanged", async () => {
    const text = sitterTermsSource.replace(/\r\n/g, "\n");
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    const hex = [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    expect(hex).toBe(SITTER_TERMS_SHA256);
  });

  test("every placeholder is filled from config, and nothing else changes", () => {
    const { body, missing } = fillSitterTerms(VALUES, "https://pacify.example/privacy", true);
    expect(missing).toEqual([]);
    expect(body).not.toMatch(PLACEHOLDER);
    for (const expected of [
      "Last updated: 15 Nov 2026 · Version 1.1",
      "(LLPIN AAA-1234, registered office at 12 MG Road, Bengaluru 560001)",
      "Priya Rao · grievance@example.com · +91 90000 00001",
      "Privacy Policy at https://pacify.example/privacy.",
      "Emergency line during bookings: +91 90000 00002",
      "Pacifyco LLP · 12 MG Road, Bengaluru 560001",
    ]) {
      expect(body).toContain(expected);
    }
    // Put the placeholders back and it's the original text again.
    const restored = body
      .replace("15 Nov 2026", "\\[DATE\\]")
      .replace("AAA-1234", "\\[INSERT\\]")
      .replace("12 MG Road, Bengaluru 560001", "\\[INSERT ADDRESS\\]")
      .replace("12 MG Road, Bengaluru 560001", "\\[REGISTERED ADDRESS\\]")
      .replace("Priya Rao", "\\[NAME\\]")
      .replace("grievance@example.com", "\\[EMAIL\\]")
      .replace("+91 90000 00001", "\\[PHONE\\]")
      .replace("https://pacify.example/privacy", "\\[LINK\\]")
      .replace("+91 90000 00002", "\\[NUMBER\\]");
    expect(restored).toBe(sitterTermsSource.replace(/\r\n/g, "\n"));
  });

  test("outside production, empty values show as test markers", () => {
    const { body, missing } = fillSitterTerms(EMPTY, "https://pacify.example/privacy", false);
    expect(missing).toEqual([]);
    expect(body).toContain("LLPIN TEST LLPIN");
    expect(body).toContain("TEST GRIEVANCE OFFICER NAME");
    expect(body).not.toMatch(PLACEHOLDER);
  });

  test("production refuses while any value is empty", () => {
    expect(fillSitterTerms({ ...VALUES, emergencyLine: "" }, "x", true).missing).toEqual(["emergency line"]);
    expect(fillSitterTerms({ ...VALUES, sitterTermsDate: "15/11/2026" }, "x", true).missing).toEqual(["date"]);
    // 7 values (the address fills two placeholders; the privacy link is always set).
    expect(fillSitterTerms(EMPTY, "x", true).missing).toHaveLength(7);
  });
});

describe("legal pages", () => {
  test("the Sitter Terms page shows the full terms, with the summary table", async () => {
    renderApp("/terms/sitter");
    expect(await screen.findByText("Pacifyco Sitter Terms of Use")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Topic" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "1. Joining Pacifyco" })).toBeTruthy();
    expect(screen.getAllByText(/TEST LLPIN/).length).toBeGreaterThan(0); // local: test markers
    // No Markdown syntax leaks into what people read.
    const article = document.querySelector("article")!.textContent!;
    expect(article).not.toMatch(/\*\*|\\|^\s*\|/m);
  });

  test.each([
    ["/terms/parent", "Terms of service for parents"],
    ["/privacy", "Privacy policy"],
  ])("%s is a marked draft with a version", async (path, heading) => {
    renderApp(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeTruthy();
    expect(screen.getByText("DRAFT — NOT LEGALLY REVIEWED.")).toBeTruthy();
    expect(screen.getByText("Version 0.1-draft")).toBeTruthy();
  });

  test("every page links to the terms and privacy policy", async () => {
    renderApp("/");
    const legal = await screen.findByRole("navigation", { name: "Legal" });
    const links = [...legal.querySelectorAll("a")].map((link) => link.getAttribute("href"));
    expect(links).toEqual(["/terms/parent", "/terms/sitter", "/privacy"]);
  });
});
