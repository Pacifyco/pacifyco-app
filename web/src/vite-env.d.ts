/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_SUPABASE_URL?: string;
  readonly VITE_SUPABASE_ANON_KEY?: string;
  readonly VITE_SENTRY_DSN?: string;
  readonly VITE_ENVIRONMENT?: "local" | "staging" | "production";
  readonly VITE_PACIFY_LLPIN?: string;
  readonly VITE_PACIFY_REGISTERED_ADDRESS?: string;
  readonly VITE_GRIEVANCE_OFFICER_NAME?: string;
  readonly VITE_GRIEVANCE_OFFICER_EMAIL?: string;
  readonly VITE_GRIEVANCE_OFFICER_PHONE?: string;
  readonly VITE_EMERGENCY_LINE?: string;
  readonly VITE_SITTER_TERMS_DATE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
