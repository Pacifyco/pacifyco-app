import { screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import familyTermsSource from "../content/family-terms-v1.0.md?raw";
import sitterConsentSource from "../content/sitter-consent-v1.0.md?raw";
import sitterTermsSource from "../content/sitter-terms-v1.1.md?raw";
import { renderApp } from "../test/renderApp";
import { fillFamilyTerms, fillSitterTerms } from "./legal";

// Fingerprint of the Sitter Terms of Use v1.1 (CLAUDE.md 7). Until the first release to main, Reuben's changes
// go in place and this is updated; after that, if this fails, undo the edit: a new version is a new file.
const SITTER_TERMS_SHA256 = "bc5592a1703a1076a9194f1ed70c18a4b6636e56b3ec3704eaa0ca7810e0ac60";
// The same for the Family Terms of Use v1.0 (from Reuben's .docx, brought in line with CLAUDE.md 2026-11-13).
const FAMILY_TERMS_SHA256 = "2f80f71726f0f7e0865ee8f8d1afc2b416b78cf508fe90792300d8929054829e";
// The sitter consent v1.0 (converted word for word from Reuben's "Sitter consent" .docx, 2026-11-12).
const SITTER_CONSENT_SHA256 = "66196167b2bd055705e3fb417cef19803b1aa417b7757ac3ae53f724d7655433";

async function sha256(source: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(source.replace(/\r\n/g, "\n")));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

const VALUES = {
  llpin: "AAA-1234",
  address: "12 MG Road, Bengaluru 560001",
  grievanceName: "Priya Rao",
  grievanceEmail: "grievance@example.com",
  grievancePhone: "+91 90000 00001",
  emergencyLine: "+91 90000 00002",
  familyIntroFee: "15,000",
};
const EMPTY = Object.fromEntries(Object.keys(VALUES).map((key) => [key, ""])) as typeof VALUES;
// A placeholder as written in the terms: \[UPPER CASE\]
const PLACEHOLDER = /\\\[[A-Z ]+\\\]/;

describe("Sitter Terms of Use v1.1", () => {
  test("wording is unchanged", async () => {
    expect(await sha256(sitterTermsSource)).toBe(SITTER_TERMS_SHA256);
  });

  test("every placeholder is filled from config, and nothing else changes", () => {
    const { body, missing } = fillSitterTerms(VALUES, "https://pacify.example/privacy", true);
    expect(missing).toEqual([]);
    expect(body).not.toMatch(PLACEHOLDER);
    for (const expected of [
      "Last updated: 13 Nov 2026",
      "(LLPIN AAA-1234, registered office at 12 MG Road, Bengaluru 560001)",
      "Priya Rao · grievance@example.com · +91 90000 00001",
      "Privacy Policy at https://pacify.example/privacy.",
      "Emergency line during bookings: +91 90000 00002",
      "Pacifyco · 12 MG Road, Bengaluru 560001",
    ]) {
      expect(body).toContain(expected);
    }
    // Put the placeholders back and it's the original text again.
    const restored = body
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
    // 6 values (the address fills two placeholders; the privacy link is always set). The "Last updated"
    // date is written in the terms (13 Nov 2026), with no version shown (Reuben, 2026-11-13).
    expect(fillSitterTerms(EMPTY, "x", true).missing).toHaveLength(6);
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

  test("placeholders are filled, and the introduction fee isn't mistaken for the LLPIN", () => {
    const { body, missing } = fillFamilyTerms(VALUES, "https://pacify.example/privacy", true);
    expect(missing).toEqual([]);
    expect(body).not.toMatch(PLACEHOLDER);
    for (const expected of [
      "Last updated: 13 Nov 2026",
      "(LLPIN AAA-1234, registered office at 12 MG Road, Bengaluru 560001)",
      "one-time introduction fee of **₹15,000**",
      "Priya Rao · grievance@example.com · +91 90000 00001",
      "24-hour safety line during bookings: +91 90000 00002.",
      "Privacy Policy at https://pacify.example/privacy.",
      "Safety line during bookings: +91 90000 00002",
    ]) {
      expect(body).toContain(expected);
    }
    expect(body).not.toContain("₹AAA-1234");
  });

  test("production refuses while any of its 7 values is empty", () => {
    expect(fillFamilyTerms({ ...VALUES, familyIntroFee: "" }, "x", true).missing).toEqual(["introduction fee"]);
    expect(fillFamilyTerms(EMPTY, "x", true).missing).toHaveLength(7);
  });

  test("outside production, empty values show as test markers", () => {
    const { body } = fillFamilyTerms(EMPTY, "x", false);
    expect(body).toContain("introduction fee of **TEST INTRODUCTION FEE**");
    expect(body).toContain("LLPIN TEST LLPIN");
    expect(body).not.toMatch(PLACEHOLDER);
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

  test("the privacy policy is a marked draft with a version", async () => {
    renderApp("/privacy");
    expect(await screen.findByRole("heading", { level: 1, name: "Privacy policy" })).toBeTruthy();
    expect(screen.getByText("DRAFT — NOT LEGALLY REVIEWED.")).toBeTruthy();
    expect(screen.getByText("Version 0.1-draft")).toBeTruthy();
  });

  test("every page's footer links only to the privacy policy", async () => {
    renderApp("/");
    const legal = await screen.findByRole("navigation", { name: "Legal" });
    const links = [...legal.querySelectorAll("a")].map((link) => link.getAttribute("href"));
    expect(links).toEqual(["/privacy"]);
    expect(screen.queryByRole("link", { name: "Components" })).toBeNull();
  });
});
