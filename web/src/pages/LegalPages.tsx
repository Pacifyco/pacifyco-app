import { useMemo } from "react";
import { PRIVACY_POLICY, fillFamilyTerms, fillSitterTerms, type FilledTerms } from "../lib/legal";
import { Markdown } from "../lib/markdown";

// Public pages: anyone can read the terms and privacy policy, signed in or not.

function LegalArticle({ body, version }: { body: string; version?: string }) {
  return (
    <article className="mx-auto max-w-[72ch]">
      <Markdown body={body} />
      {version && <p className="mt-6 text-small text-muted">Version {version}</p>}
    </article>
  );
}

// CLAUDE.md 7: never serve final terms in production while a placeholder is empty.
function FinalTerms({ name, fill }: { name: string; fill: () => FilledTerms }) {
  const terms = useMemo(() => fill(), [fill]);
  if (terms.missing.length) {
    return (
      <section className="mx-auto max-w-[62ch] text-center">
        <h1>The {name} aren't available yet.</h1>
        <p className="mt-4 text-muted">Please check back soon, or contact us at query.pacifyco@gmail.com.</p>
      </section>
    );
  }
  return <LegalArticle body={terms.body} />;
}

export function SitterTermsPage() {
  return <FinalTerms name="Sitter Terms" fill={fillSitterTerms} />;
}

export function ParentTermsPage() {
  return <FinalTerms name="Family Terms" fill={fillFamilyTerms} />;
}

export function PrivacyPolicyPage() {
  return <LegalArticle body={PRIVACY_POLICY.body} version={PRIVACY_POLICY.meta.version} />;
}
