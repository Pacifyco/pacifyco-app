// Values from the root .env (VITE_* only; these are visible in the browser, so never secrets).
export const config = {
  apiUrl: (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, ""),
  environment: import.meta.env.VITE_ENVIRONMENT || "local",
  // Sentry DSNs are public by design (they only allow sending errors), so this is fine in the browser.
  sentryDsn: import.meta.env.VITE_SENTRY_DSN || "",
  // Supabase is used for sign-in only. The publishable key is public by design: the Data API is off and
  // no table can be read from the browser (CLAUDE.md section 5).
  supabaseUrl: (import.meta.env.VITE_SUPABASE_URL || "").replace(/\/$/, ""),
  supabaseKey: import.meta.env.VITE_SUPABASE_ANON_KEY || "",
} as const;
