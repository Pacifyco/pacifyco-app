// Where the end-to-end pieces run, and the API's test-only settings (playwright.config.ts starts them).

export const FAKE = "http://localhost:54321";
export const API = "http://localhost:8001";
export const WEB = "http://localhost:5174";

// The API's Python: the venv locally, or E2E_PYTHON (CI sets it to the runner's python).
export const python =
  process.env.E2E_PYTHON ?? (process.platform === "win32" ? String.raw`.venv\Scripts\python.exe` : ".venv/bin/python");

// Test-only values, nothing real. The encryption key only protects fake data in a throwaway database.
export const apiEnv = {
  ENVIRONMENT: "local",
  DATABASE_URL: "postgresql+psycopg://pacifyco:pacifyco@localhost:5432/pacifyco_e2e",
  SUPABASE_URL: FAKE,
  SUPABASE_JWKS_URL: "",
  SUPABASE_SERVICE_ROLE_KEY: "e2e-not-a-secret",
  CORS_ORIGINS: WEB,
  PUBLIC_WEB_URL: WEB,
  FIELD_ENCRYPTION_KEY: "e1B_ERGTEpy-85Yk_z0eCsWeIwB9gYF5bVvSHaTGC6I=",
  NOMINATIM_URL: `${FAKE}/nominatim/search`,
  SENTRY_DSN: "",
};

