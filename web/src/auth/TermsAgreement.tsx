import { Link } from "react-router";
import { Checkbox } from "../components/ui";
import sitterConsentSource from "../content/sitter-consent-v1.0.md?raw";
import {
  FAMILY_TERMS_VERSION,
  PRIVACY_POLICY,
  SITTER_TERMS_VERSION,
  fillFamilyTerms,
  fillSitterTerms,
} from "../lib/legal";
import { parseDocument } from "../lib/markdown";
import type { Role, TermsKind, TermsVersion } from "./useMe";

// Click-wrap (CLAUDE.md 7): an unticked box, links that open the full text, and the versions this copy
// of the app shows. The API checks they're the current ones and records the acceptance. The box is on
// each role's consent page (moved from sign-up, decided 2026-11-12): /parent/consent and /sitter/consent.

export const SITTER_CONSENT = parseDocument(sitterConsentSource);

const DOCS: Record<TermsKind, { label: string; path: string; version: string }> = {
  parent_terms: { label: "Family Terms of Use", path: "/terms/parent", version: FAMILY_TERMS_VERSION },
  sitter_terms: { label: "Sitter Terms of Use", path: "/terms/sitter", version: SITTER_TERMS_VERSION },
  privacy_policy: { label: "Privacy policy", path: "/privacy", version: PRIVACY_POLICY.meta.version ?? "" },
  sitter_consent: { label: "Sitter consent", path: "/sitter/consent", version: SITTER_CONSENT.meta.version ?? "" },
};

/** The terms and privacy policy in the role's "I agree to…" box. */
export function requiredTerms(role: Exclude<Role, "admin">): TermsKind[] {
  return [role === "parent" ? "parent_terms" : "sitter_terms", "privacy_policy"];
}

/** True when the API asks for a version this copy of the app doesn't show: it needs a reload. */
export function termsOutdated(toAccept: TermsVersion[]): boolean {
  return toAccept.some((item) => DOCS[item.kind].version !== item.version);
}

/** What to send as `accepted`: each kind at the version this page showed. */
export function shownVersions(kinds: TermsKind[]): TermsVersion[] {
  return kinds.map((kind) => ({ kind, version: DOCS[kind].version }));
}

/** False in production while one of the role's terms has an empty placeholder: nobody can agree to it yet. */
export function termsReady(role: Exclude<Role, "admin">): boolean {
  return (role === "parent" ? fillFamilyTerms() : fillSitterTerms()).missing.length === 0;
}

export const AGREE_ERROR = "Please tick the box to agree before you continue.";

function DocLink({ kind }: { kind: TermsKind }) {
  return (
    <Link to={DOCS[kind].path} target="_blank" rel="noopener">
      {DOCS[kind].label}
    </Link>
  );
}

export function TermsCheckbox({
  kinds,
  checked,
  onChange,
  error,
}: {
  kinds: TermsKind[];
  checked: boolean;
  onChange: (checked: boolean) => void;
  error?: string;
}) {
  const [first, ...rest] = kinds;
  return (
    <Checkbox
      className="text-left"
      checked={checked}
      onChange={(event) => onChange(event.target.checked)}
      error={error}
      label={
        <>
          I agree to the <DocLink kind={first} />
          {rest.map((kind) => (
            <span key={kind}>
              {" and "}
              <DocLink kind={kind} />
            </span>
          ))}
          .
        </>
      }
    />
  );
}
