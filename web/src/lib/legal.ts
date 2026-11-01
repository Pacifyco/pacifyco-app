import { config } from "../config";
import familyTermsSource from "../content/family-terms-v1.0.md?raw";
import privacySource from "../content/privacy-policy.md?raw";
import sitterTermsSource from "../content/sitter-terms-v1.1.md?raw";
import { formatDate } from "./format";
import { parseDocument } from "./markdown";

// Legal documents (CLAUDE.md 7). The Sitter Terms of Use v1.1 and the Family Terms of Use v1.0 are final:
// their wording is never changed; only their bracketed placeholders are filled from config here. In
// production a document with an empty placeholder isn't shown and can't be accepted. The privacy policy
// is still a placeholder until legal review.

export const SITTER_TERMS_VERSION = "1.1";
export const FAMILY_TERMS_VERSION = "1.0";
export const PRIVACY_POLICY = parseDocument(privacySource);

type Values = typeof config.legal;
type Placeholder = { token: string; label: string; value: (values: Values, privacyUrl: string) => string };

// Placeholders both documents share, exactly as written (Markdown-escaped brackets).
const SHARED: Placeholder[] = [
  { token: "\\[INSERT\\]", label: "LLPIN", value: (v) => v.llpin },
  { token: "\\[INSERT ADDRESS\\]", label: "registered address", value: (v) => v.address },
  { token: "\\[REGISTERED ADDRESS\\]", label: "registered address", value: (v) => v.address },
  { token: "\\[NAME\\]", label: "Grievance Officer name", value: (v) => v.grievanceName },
  { token: "\\[EMAIL\\]", label: "Grievance Officer email", value: (v) => v.grievanceEmail },
  { token: "\\[PHONE\\]", label: "Grievance Officer phone", value: (v) => v.grievancePhone },
  { token: "\\[NUMBER\\]", label: "emergency line", value: (v) => v.emergencyLine },
  { token: "\\[LINK\\]", label: "privacy policy link", value: (_, url) => url },
];

const SITTER: Placeholder[] = [
  { token: "\\[DATE\\]", label: "date", value: (v) => termsDate(v.sitterTermsDate) },
  ...SHARED,
];

const FAMILY: Placeholder[] = [
  // Section 7.2's "₹[INSERT]" is the introduction fee, not the LLPIN: fill it before the shared ones.
  { token: "₹\\[INSERT\\]", label: "introduction fee", value: (v) => (v.familyIntroFee ? `₹${v.familyIntroFee}` : "") },
  { token: "\\[DATE\\]", label: "date", value: (v) => termsDate(v.familyTermsDate) },
  ...SHARED,
];

function termsDate(isoDate: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) return "";
  const date = new Date(`${isoDate}T00:00:00+05:30`);
  return Number.isNaN(date.getTime()) ? "" : formatDate(date);
}

export type FilledTerms = { body: string; missing: string[] };

/** Fill a document's placeholders. Outside production, empty values become visible TEST markers; in
 * production they're reported in `missing`, and the document must not be shown or accepted. */
function fill(
  source: string,
  placeholders: Placeholder[],
  values: Values,
  privacyUrl: string,
  production: boolean,
): FilledTerms {
  const missing = new Set<string>();
  let body = source.replace(/\r\n/g, "\n");
  for (const { token, label, value } of placeholders) {
    const filled = value(values, privacyUrl).trim();
    if (!filled) missing.add(label);
    body = body.split(token).join(filled || (production ? "" : `TEST ${label.toUpperCase()}`));
  }
  return { body, missing: production ? [...missing] : [] };
}

const defaults = () =>
  [config.legal, `${window.location.origin}/privacy`, config.environment === "production"] as const;

export function fillSitterTerms(
  values: Values = defaults()[0],
  privacyUrl: string = defaults()[1],
  production: boolean = defaults()[2],
): FilledTerms {
  return fill(sitterTermsSource, SITTER, values, privacyUrl, production);
}

export function fillFamilyTerms(
  values: Values = defaults()[0],
  privacyUrl: string = defaults()[1],
  production: boolean = defaults()[2],
): FilledTerms {
  return fill(familyTermsSource, FAMILY, values, privacyUrl, production);
}
