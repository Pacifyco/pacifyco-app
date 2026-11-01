import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

// CLAUDE.md 9 "Sitter terms": production refuses to serve them while a placeholder is empty. config.ts
// reads import.meta.env when first imported, so each test loads fresh modules with production settings.

const FILLED = {
  VITE_ENVIRONMENT: "production",
  VITE_PACIFY_LLPIN: "AAA-1234",
  VITE_PACIFY_REGISTERED_ADDRESS: "12 MG Road, Bengaluru 560001",
  VITE_GRIEVANCE_OFFICER_NAME: "Priya Rao",
  VITE_GRIEVANCE_OFFICER_EMAIL: "grievance@example.com",
  VITE_GRIEVANCE_OFFICER_PHONE: "+91 90000 00001",
  VITE_EMERGENCY_LINE: "+91 90000 00002",
  VITE_SITTER_TERMS_DATE: "2026-11-15",
};

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
  test.each(Object.keys(FILLED).filter((name) => name !== "VITE_ENVIRONMENT"))(
    "hidden, and sitters can't agree, while %s is empty",
    async (name) => {
      const { SitterTermsPage, sitterTermsReady } = await loadWith({ ...FILLED, [name]: "" });
      render(<SitterTermsPage />);
      expect(screen.getByRole("heading", { name: "The Sitter Terms aren't available yet." })).toBeTruthy();
      expect(screen.queryByText("Pacifyco Sitter Terms of Use")).toBeNull();
      expect(sitterTermsReady()).toBe(false);
    },
  );

  test("shown, with no test markers, once every value is set", async () => {
    const { SitterTermsPage, sitterTermsReady } = await loadWith(FILLED);
    render(<SitterTermsPage />);
    expect(screen.getByText("Pacifyco Sitter Terms of Use")).toBeTruthy();
    expect(screen.getByText(/Last updated: 15 Nov 2026/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/TEST /);
    expect(sitterTermsReady()).toBe(true);
  });
});
