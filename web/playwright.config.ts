import { defineConfig, devices } from "@playwright/test";
import { API, FAKE, WEB, apiEnv, python } from "./e2e/env";

// End-to-end tests (CLAUDE.md 9: Playwright smoke tests for the main journeys). They run the real web app
// against the real API and a fresh local database, in a real browser. Only the outside services are stand-ins
// (e2e/fake-services.mjs): Supabase sign-in keys and file storage, and OpenStreetMap.
//
// Needs the local Postgres (`docker compose up -d --wait`) and the API's Python environment.
// Run from web/: npm run e2e

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { baseURL: WEB, trace: "retain-on-failure", screenshot: "only-on-failure", ...devices["Pixel 7"] },
  webServer: [
    {
      command: "node e2e/fake-services.mjs",
      url: `${FAKE}/auth/v1/.well-known/jwks.json`,
      reuseExistingServer: !process.env.CI,
    },
    {
      // A fresh database every run, then the API.
      command: `${python} e2e_database.py && ${python} -m uvicorn app.main:app --port 8001`,
      cwd: "../api",
      env: apiEnv,
      url: `${API}/health`,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npx vite --port 5174 --strictPort",
      env: {
        VITE_API_URL: API,
        VITE_SUPABASE_URL: FAKE,
        VITE_SUPABASE_ANON_KEY: "e2e-not-a-secret",
        VITE_ENVIRONMENT: "local",
        VITE_SENTRY_DSN: "",
      },
      url: WEB,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
