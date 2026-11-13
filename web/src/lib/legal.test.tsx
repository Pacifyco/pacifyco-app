import { screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import familyTermsSource from "../content/family-terms-v1.0.md?raw";
import sitterConsentSource from "../content/sitter-consent-v1.0.md?raw";
import sitterTermsSource from "../content/sitter-terms-v1.1.md?raw";
import { renderApp } from "../test/renderApp";
import { fillFamilyTerms, fillSitterTerms } from "./legal";

// Fingerprint of the Sitter Terms of Use v1.1 (CLAUDE.md 7). Until the first release to main, Reuben's changes
// go in place and this is updated; after that, if this fails, undo the edit: a new version is a new file.
const SITTER_TERMS_SHA256 = "57691377826cbd7e47fc0cd805acdd8ccd35cc91ef46b130cb34d4d5898a52f4";
// The same for the Family Terms of Use v1.0 (from Reuben's .docx, brought in line with CLAUDE.md 2026-11-13).
const FAMILY_TERMS_SHA256 = "a1c103f3c382b3a91cb24c9b4abf28e886467dad8a5471d3038a0027852467b6";
// The sitter consent v1.0 (converted word for word from Reuben's "Sitter consent" .docx, 2026-11-12).
const SITTER_CONSENT_SHA256 = "66196167b2bd055705e3fb417cef19803b1aa417b7757ac3ae53f724d7655433";

async function sha256(source: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(source.replace(/\r\n/g, "\n")));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

const VALUES = {
  grievanceName: "Priya Rao",
  grievanceEmail: "grievance@example.com",
  grievancePhone: "+91 90000 00001",
  familyIntroFee: "15,000",
};
const EMPTY = Object.fromEntries(Object.keys(VALUES).map((key) => [key, ""])) as typeof VALUES;
// A placeholder as written in the terms: \[UPPER CASE\]
const PLACEHOLDER = /\\\[[A-Z ]+\\\]/;
// Taken out of both terms (Reuben, 2026-11-13): no LLPIN, registered office or emergency/safety line.
const REMOVED = /LLPIN|registered office|REGISTERED ADDRESS|Emergency line|safety line/i;

describe("Sitter Terms of Use v1.1", () => {
  test("wording is unchanged", async () => {
    expect(await sha256(sitterTermsSource)).toBe(SITTER_TERMS_SHA256);
  });

  test("every placeholder is filled from config, and nothing else changes", () => {
    const { body, missing } = fillSitterTerms(VALUES, "https://pacify.example/privacy", true);
    expect(missing).toEqual([]);
    expect(body).not.toMatch(PLACEHOLDER);
    expect(body).not.toMatch(REMOVED);
    for (const expected of [
      "Last updated: 13 Nov 2026",
      "between you and **Pacifyco** (",
      "Priya Rao · grievance@example.com · +91 90000 00001",
      "Privacy Policy at https://pacify.example/privacy.",
      "founders@pacifyco.in · +91 8848873841",
    ]) {
      expect(body).toContain(expected);
    }
    // Put the placeholders back and it's the original text again.
    const restored = body
      .replace("Priya Rao", "\\[NAME\\]")
      .replace("grievance@example.com", "\\[EMAIL\\]")
      .replace("+91 90000 00001", "\\[PHONE\\]")
      .replace("https://pacify.example/privacy", "\\[LINK\\]");
    expect(restored).toBe(sitterTermsSource.replace(/\r\n/g, "\n"));
  });

  test("outside production, empty values show as test markers", () => {
    const { body, missing } = fillSitterTerms(EMPTY, "https://pacify.example/privacy", false);
    expect(missing).toEqual([]);
    expect(body).toContain("TEST GRIEVANCE OFFICER NAME");
    expect(body).not.toMatch(PLACEHOLDER);
  });

  test("production refuses while any value is empty", () => {
    expect(fillSitterTerms({ ...VALUES, grievancePhone: "" }, "x", true).missing).toEqual(["Grievance Officer phone"]);
    // The Grievance Officer's name, email and phone (the privacy link is always set).
    expect(fillSitterTerms(EMPTY, "x", true).missing).toHaveLength(3);
  });
});

describe("Sitter consent v1.0", () => {
  test("wording is unchanged", async () => {
    expect(await sha256(sitterConsentSource)).toBe(SITTER_CONSENT_SHA256);
  });
});

describe("Family Terms of Use v1.0", () => {
  test("wording is unchanged", async () => {
    expect(await sha256(familyTermsSource)).toBe(FAMILY_TERMS_SHA256);
  });

  test("placeholders are filled", () => {
    const { body, missing } = fillFamilyTerms(VALUES, "https://pacify.example/privacy", true);
    expect(missing).toEqual([]);
    expect(body).not.toMatch(PLACEHOLDER);
    expect(body).not.toMatch(REMOVED);
    for (const expected of [
      "Last updated: 13 Nov 2026",
      "one-time introduction fee of **₹15,000**",
      "Priya Rao · grievance@example.com · +91 90000 00001 · Monday to Saturday, 10 am to 6 pm.",
      "Privacy Policy at https://pacify.example/privacy.",
      "Add one emergency contact",
    ]) {
      expect(body).toContain(expected);
    }
    expect(body).not.toMatch(/authorised adult/i); // removed (Reuben, 2026-11-13)
  });

  test("production refuses while any of its 4 values is empty", () => {
    expect(fillFamilyTerms({ ...VALUES, familyIntroFee: "" }, "x", true).missing).toEqual(["introduction fee"]);
    expect(fillFamilyTerms(EMPTY, "x", true).missing).toHaveLength(4);
  });

  test("outside production, empty values show as test markers", () => {
    const { body } = fillFamilyTerms(EMPTY, "x", false);
    expect(body).toContain("introduction fee of **TEST INTRODUCTION FEE**");
    expect(body).not.toMatch(PLACEHOLDER);
  });
});

describe("legal pages", () => {
  test("the Sitter Terms page shows the full terms, with the summary table", async () => {
    renderApp("/terms/sitter");
    expect(await screen.findByText("Pacifyco Sitter Terms of Use")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Topic" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "1. Joining Pacifyco" })).toBeTruthy();
    expect(screen.getAllByText(/TEST GRIEVANCE OFFICER/).length).toBeGreaterThan(0); // local: test markers
    // No Markdown syntax leaks into what people read.
    const article = document.querySelector("article")!.textContent!;
    expect(article).not.toMatch(/\*\*|\\|^\s*\|/m);
  });

  test("the Family Terms page shows the full terms, tables included", async () => {
    renderApp("/terms/parent");
    expect(await screen.findByText("Pacifyco Family Terms of Use")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "4. Plans, payment and overtime" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Price per hour" })).toBeTruthy();
    // In line with CLAUDE.md (Reuben, 2026-11-13): plans, 18 months, no interviews, packs or Aadhaar.
    const text = document.querySelector("article")!.textContent!;
    expect(text).toContain("18 months and above");
    expect(text).not.toMatch(/hour pack|interview|Aadhaar|one-time password/i);
    const article = document.querySelector("article")!.textContent!;
    expect(article).not.toMatch(/\*\*|\\|^\s*\|/m);
  });

  test("the privacy policy is a generic policy with a date and no version", async () => {
    renderApp("/privacy");
    expect(await screen.findByRole("heading", { level: 1, name: "Privacy policy" })).toBeTruthy();
    // A generic policy (Reuben, 2026-11-13): no draft marker, a "Last updated" date and no version.
    expect(screen.queryByText(/DRAFT/)).toBeNull();
    expect(screen.getByText("Last updated: 13 Nov 2026")).toBeTruthy();
    expect(screen.queryByText(/^Version /)).toBeNull();
    expect(screen.getByRole("heading", { name: "4. Children's data" })).toBeTruthy();
  });

  test("every page's footer links only to the privacy policy", async () => {
    renderApp("/");
    const legal = await screen.findByRole("navigation", { name: "Legal" });
    const links = [...legal.querySelectorAll("a")].map((link) => link.getAttribute("href"));
    expect(links).toEqual(["/privacy"]);
    expect(screen.queryByRole("link", { name: "Components" })).toBeNull();
  });
});
