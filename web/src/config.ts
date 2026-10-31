// Values from the root .env (VITE_* only; these are visible in the browser, so never secrets).
export const config = {
  apiUrl: (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, ""),
  environment: import.meta.env.VITE_ENVIRONMENT || "local",
} as const;
