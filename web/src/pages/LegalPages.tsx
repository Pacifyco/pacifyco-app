import { useMemo } from "react";
import { PARENT_TERMS, PRIVACY_POLICY, fillSitterTerms } from "../lib/legal";
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

export function SitterTermsPage() {
  const terms = useMemo(() => fillSitterTerms(), []);
  // CLAUDE.md 7: never serve the Sitter Terms in production while a placeholder is empty.
  if (terms.missing.length) {
    return (
      <section className="mx-auto max-w-[62ch] text-center">
        <h1>The Sitter Terms aren't available yet.</h1>
        <p className="mt-4 text-muted">Please check back soon, or contact us at query.pacifyco@gmail.com.</p>
      </section>
    );
  }
  return <LegalArticle body={terms.body} />;
}

export function ParentTermsPage() {
  return <LegalArticle body={PARENT_TERMS.body} version={PARENT_TERMS.meta.version} />;
}

export function PrivacyPolicyPage() {
  return <LegalArticle body={PRIVACY_POLICY.body} version={PRIVACY_POLICY.meta.version} />;
}
