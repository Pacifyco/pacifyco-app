import { config } from "../config";
import parentTermsSource from "../content/parent-terms.md?raw";
import privacySource from "../content/privacy-policy.md?raw";
import sitterTermsSource from "../content/sitter-terms-v1.1.md?raw";
import { formatDate } from "./format";
import { parseDocument } from "./markdown";

// Legal documents (CLAUDE.md 7). The Sitter Terms of Use v1.1 is final: its wording is never changed;
// only its bracketed placeholders are filled from config here. The parent terms and privacy policy are
// placeholders until legal review.

export const SITTER_TERMS_VERSION = "1.1";
export const PARENT_TERMS = parseDocument(parentTermsSource);
export const PRIVACY_POLICY = parseDocument(privacySource);

type Values = typeof config.legal;

// Each placeholder exactly as written in the terms (Markdown-escaped brackets) and where its value comes from.
const PLACEHOLDERS: { token: string; label: string; value: (values: Values, privacyUrl: string) => string }[] = [
  { token: "\\[DATE\\]", label: "date", value: (v) => termsDate(v.sitterTermsDate) },
  { token: "\\[INSERT\\]", label: "LLPIN", value: (v) => v.llpin },
  { token: "\\[INSERT ADDRESS\\]", label: "registered address", value: (v) => v.address },
  { token: "\\[REGISTERED ADDRESS\\]", label: "registered address", value: (v) => v.address },
  { token: "\\[NAME\\]", label: "Grievance Officer name", value: (v) => v.grievanceName },
  { token: "\\[EMAIL\\]", label: "Grievance Officer email", value: (v) => v.grievanceEmail },
  { token: "\\[PHONE\\]", label: "Grievance Officer phone", value: (v) => v.grievancePhone },
  { token: "\\[NUMBER\\]", label: "emergency line", value: (v) => v.emergencyLine },
  { token: "\\[LINK\\]", label: "privacy policy link", value: (_, url) => url },
];

function termsDate(isoDate: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) return "";
  const date = new Date(`${isoDate}T00:00:00+05:30`);
  return Number.isNaN(date.getTime()) ? "" : formatDate(date);
}

export type FilledTerms = { body: string; missing: string[] };

/** Fill the Sitter Terms placeholders. Outside production, empty values become visible test markers;
 * in production they're reported in `missing`, and the terms must not be shown. */
export function fillSitterTerms(
  values: Values = config.legal,
  privacyUrl = `${window.location.origin}/privacy`,
  production = config.environment === "production",
): FilledTerms {
  const missing = new Set<string>();
  let body = sitterTermsSource.replace(/\r\n/g, "\n");
  for (const { token, label, value } of PLACEHOLDERS) {
    const filled = value(values, privacyUrl).trim();
    if (!filled) missing.add(label);
    body = body.split(token).join(filled || (production ? "" : `TEST ${label.toUpperCase()}`));
  }
  return { body, missing: production ? [...missing] : [] };
}
