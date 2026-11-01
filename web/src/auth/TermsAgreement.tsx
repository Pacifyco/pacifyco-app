import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";
import { Button, Checkbox } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { PARENT_TERMS, PRIVACY_POLICY, SITTER_TERMS_VERSION, fillSitterTerms } from "../lib/legal";
import { useAuth } from "./AuthProvider";
import type { Me, Role, TermsKind, TermsVersion } from "./useMe";

// Click-wrap (CLAUDE.md 7): an unticked box, links that open the full text, and the versions this copy
// of the app shows. The API checks they're the current ones and records the acceptance.

const DOCS: Record<TermsKind, { label: string; path: string; version: string }> = {
  parent_terms: { label: "Terms of service", path: "/terms/parent", version: PARENT_TERMS.meta.version ?? "" },
  sitter_terms: { label: "Sitter Terms of Use", path: "/terms/sitter", version: SITTER_TERMS_VERSION },
  privacy_policy: { label: "Privacy policy", path: "/privacy", version: PRIVACY_POLICY.meta.version ?? "" },
};

export function requiredTerms(role: Exclude<Role, "admin">): TermsKind[] {
  return [role === "parent" ? "parent_terms" : "sitter_terms", "privacy_policy"];
}

/** What to send as `accepted`: each kind at the version this page showed. */
export function shownVersions(kinds: TermsKind[]): TermsVersion[] {
  return kinds.map((kind) => ({ kind, version: DOCS[kind].version }));
}

/** False in production while a Sitter Terms placeholder is empty: sitters can't agree to it yet. */
export function sitterTermsReady(): boolean {
  return fillSitterTerms().missing.length === 0;
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

// Shown in place of an area when the person must accept current terms first: new versions, or accounts
// made before click-wrap existed.
export function AcceptTermsPage({ toAccept }: { toAccept: TermsVersion[] }) {
  const { userId } = useAuth();
  const queryClient = useQueryClient();
  const [ticked, setTicked] = useState(false);
  const [error, setError] = useState<string>();
  const kinds = toAccept.map((item) => item.kind);
  // This copy of the app shows older texts than the API requires: it needs a reload.
  const outdated = toAccept.some((item) => DOCS[item.kind].version !== item.version);
  const blockedSitter = kinds.includes("sitter_terms") && !sitterTermsReady();

  const accept = useMutation({
    mutationFn: () =>
      apiFetch<Me>("/me/terms", { method: "POST", body: JSON.stringify({ accepted: shownVersions(kinds) }) }),
    onSuccess: (me) => queryClient.setQueryData(["me", userId], me),
  });

  function submit() {
    if (!ticked) return setError(AGREE_ERROR);
    setError(undefined);
    accept.mutate();
  }

  return (
    <section className="mx-auto max-w-[36rem] text-center">
      <h1>Please read and accept our terms.</h1>
      <p className="mt-4 text-muted">
        Before you carry on, please read these. They open in a new tab. When we change them, we'll ask you again.
      </p>
      {outdated ? (
        <p role="alert" className="mt-6 text-small text-danger">
          Our terms have been updated. Please reload the page to read the new version.
        </p>
      ) : blockedSitter ? (
        <p className="mt-6 text-muted">The Sitter Terms aren't available yet. Please check back soon.</p>
      ) : (
        <div className="mt-6 flex flex-col gap-5 rounded-lg bg-surface-sunken p-5">
          <TermsCheckbox kinds={kinds} checked={ticked} onChange={setTicked} error={error} />
          {accept.error instanceof ApiError && (
            <p role="alert" className="text-small text-danger">
              {accept.error.message}
            </p>
          )}
          <Button loading={accept.isPending} onClick={submit}>
            I agree
          </Button>
        </div>
      )}
    </section>
  );
}
