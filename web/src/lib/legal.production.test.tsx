import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

// CLAUDE.md 9 "Sitter terms": production refuses to serve them while a placeholder is empty. config.ts
// reads import.meta.env when first imported, so each test loads fresh modules with production settings.

const FILLED: Record<string, string> = {
  VITE_ENVIRONMENT: "production",
  VITE_PACIFY_LLPIN: "AAA-1234",
  VITE_PACIFY_REGISTERED_ADDRESS: "12 MG Road, Bengaluru 560001",
  VITE_GRIEVANCE_OFFICER_NAME: "Priya Rao",
  VITE_GRIEVANCE_OFFICER_EMAIL: "grievance@example.com",
  VITE_GRIEVANCE_OFFICER_PHONE: "+91 90000 00001",
  VITE_EMERGENCY_LINE: "+91 90000 00002",
  VITE_SITTER_TERMS_DATE: "2026-11-15",
  VITE_FAMILY_TERMS_DATE: "2026-11-20",
  VITE_FAMILY_INTRO_FEE: "15,000",
};
const SITTER_VARS = Object.keys(FILLED).filter((name) => !/ENVIRONMENT|FAMILY/.test(name));
const FAMILY_VARS = Object.keys(FILLED).filter((name) => !/ENVIRONMENT|SITTER/.test(name));

async function loadWith(env: Record<string, string>) {
  for (const [name, value] of Object.entries(env)) vi.stubEnv(name, value);
  vi.resetModules();
  const pages = await import("../pages/LegalPages");
  const agreement = await import("../auth/TermsAgreement");
  return { ...pages, ...agreement };
}

afterEach(() => vi.unstubAllEnvs());
// Each test re-imports the pages from scratch, which can be slow while other test files run.
vi.setConfig({ testTimeout: 30_000 });

describe("Sitter Terms in production", () => {
  test.each(SITTER_VARS)(
    "hidden, and sitters can't agree, while %s is empty",
    async (name) => {
      const { SitterTermsPage, termsReady } = await loadWith({ ...FILLED, [name]: "" });
      render(<SitterTermsPage />);
      expect(screen.getByRole("heading", { name: "The Sitter Terms aren't available yet." })).toBeTruthy();
      expect(screen.queryByText("Pacifyco Sitter Terms of Use")).toBeNull();
      expect(termsReady("sitter")).toBe(false);
    },
  );

  test("shown, with no test markers, once every value is set", async () => {
    const { SitterTermsPage, termsReady } = await loadWith(FILLED);
    render(<SitterTermsPage />);
    expect(screen.getByText("Pacifyco Sitter Terms of Use")).toBeTruthy();
    expect(screen.getByText(/Last updated: 15 Nov 2026/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/TEST /);
    expect(termsReady("sitter")).toBe(true);
  });
});

describe("Family Terms in production", () => {
  test.each(FAMILY_VARS)("hidden, and parents can't agree, while %s is empty", async (name) => {
    const { ParentTermsPage, termsReady } = await loadWith({ ...FILLED, [name]: "" });
    render(<ParentTermsPage />);
    expect(screen.getByRole("heading", { name: "The Family Terms aren't available yet." })).toBeTruthy();
    expect(screen.queryByText("Pacifyco Family Terms of Use")).toBeNull();
    expect(termsReady("parent")).toBe(false);
  });

  test("shown, with no test markers, once every value is set", async () => {
    const { ParentTermsPage, termsReady } = await loadWith(FILLED);
    render(<ParentTermsPage />);
    expect(screen.getByText("Pacifyco Family Terms of Use")).toBeTruthy();
    expect(document.body.textContent).toContain("₹15,000");
    expect(document.body.textContent).not.toMatch(/TEST /);
    expect(termsReady("parent")).toBe(true);
  });
});
