import { ApiError } from "./api";

// "Always say which field failed" (UX review 2026-11-13). The API's validation details look like
// [{"field": "body.contacts.0.phone", "message": "Value error, Please enter a 10-digit Indian mobile number"}].
// This turns them into one message per field, keyed by the path after "body" ("contacts.0.phone", "phone").

export type FieldErrors = Record<string, string>;

const GENERIC: [RegExp, string][] = [
  [/at least 1 character|field required|missing/i, "Please fill this in."],
  [/at most \d+ character/i, "That's a bit long — could you shorten it?"],
  [/valid date|date/i, "Please choose a date."],
];

function friendly(message: string): string {
  const own = message.replace(/^Value error,\s*/i, "");
  if (own !== message) return own.endsWith(".") ? own : `${own}.`;
  for (const [pattern, text] of GENERIC) if (pattern.test(message)) return text;
  return "Please check this.";
}

export function fieldErrorsFrom(error: unknown): FieldErrors {
  if (!(error instanceof ApiError) || !Array.isArray(error.details)) return {};
  const errors: FieldErrors = {};
  for (const detail of error.details as { field?: unknown; message?: unknown }[]) {
    const field = String(detail?.field ?? "").replace(/^body\.?/, "");
    if (field && !(field in errors)) errors[field] = friendly(String(detail?.message ?? ""));
  }
  return errors;
}

/** A message for the whole form, when no single field can be blamed. */
export function formErrorFrom(error: unknown, fields: FieldErrors): string | undefined {
  if (Object.keys(fields).length) return undefined;
  if (error instanceof ApiError) {
    return error.code === "validation_error" ? "Something didn't go through. Please try again." : error.message;
  }
  return "Something went wrong. Please try again.";
}

// Same rule as the API (app/services/accounts.py): Indian mobile, optionally with +91, 91 or 0.
export function isIndianMobile(raw: string): boolean {
  return /^(?:\+?91|0)?[6-9]\d{9}$/.test(raw.replace(/[\s\-().]/g, ""));
}

export const MOBILE_ERROR = "Please enter a 10-digit mobile number.";
