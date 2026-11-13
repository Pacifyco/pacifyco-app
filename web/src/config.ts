// Values from the root .env (VITE_* only; these are visible in the browser, so never secrets).
export const config = {
  apiUrl: (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, ""),
  environment: import.meta.env.VITE_ENVIRONMENT || "local",
  // Sentry DSNs are public by design (they only allow sending errors), so this is fine in the browser.
  sentryDsn: import.meta.env.VITE_SENTRY_DSN || "",
  // Supabase is used for sign-in only. The publishable key is public by design: the Data API is off and
  // no table can be read from the browser (CLAUDE.md section 5).
  supabaseUrl: (import.meta.env.VITE_SUPABASE_URL || "").trim().replace(/\/$/, ""),
  supabaseKey: (import.meta.env.VITE_SUPABASE_ANON_KEY || "").trim(),
  // Values for the Sitter and Family Terms placeholders (CLAUDE.md 7). Public information, not secrets.
  legal: {
    grievanceName: (import.meta.env.VITE_GRIEVANCE_OFFICER_NAME || "").trim(),
    grievanceEmail: (import.meta.env.VITE_GRIEVANCE_OFFICER_EMAIL || "").trim(),
    grievancePhone: (import.meta.env.VITE_GRIEVANCE_OFFICER_PHONE || "").trim(),
    // Family Terms 7.2: the one-time fee to hire a sitter directly, e.g. "15,000" (shown as ₹15,000).
    familyIntroFee: (import.meta.env.VITE_FAMILY_INTRO_FEE || "").trim(),
  },
} as const;
