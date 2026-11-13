import { ArrowLeft } from "lucide-react";
import { useCallback, useMemo } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { useHeaderBack } from "../layouts/headerBack";
import { PRIVACY_POLICY, fillFamilyTerms, fillSitterTerms, type FilledTerms } from "../lib/legal";
import { Markdown, sections } from "../lib/markdown";

// Public pages: anyone can read the terms and privacy policy, signed in or not.

/** The sections, as links: a sticky list beside the text on desktop, "Jump to section" on phones. */
function Contents({ body }: { body: string }) {
  const items = sections(body);
  if (items.length < 3) return null;
  const links = (
    <ol className="flex flex-col gap-2 text-small">
      {items.map((item) => (
        <li key={item.id}>
          <a href={`#${item.id}`} className="text-ink">
            {item.text}
          </a>
        </li>
      ))}
    </ol>
  );
  return (
    <>
      <details className="mb-5 rounded-md bg-surface-sunken px-4 py-3 lg:hidden">
        <summary className="cursor-pointer text-ui text-ink">Jump to section</summary>
        <nav aria-label="Sections" className="mt-3">
          {links}
        </nav>
      </details>
      <nav aria-label="Contents" className="sticky top-5 hidden max-h-[calc(100dvh-2.5rem)] overflow-y-auto lg:block">
        <p className="mb-3 text-eyebrow text-muted uppercase">Contents</p>
        {links}
      </nav>
    </>
  );
}

function LegalArticle({ body, version }: { body: string; version?: string }) {
  return (
    <div className="mx-auto max-w-[72rem] lg:grid lg:grid-cols-[16rem_minmax(0,72ch)] lg:justify-center lg:gap-8">
      <div className="lg:order-none">
        <Contents body={body} />
      </div>
      <article className="mx-auto max-w-[72ch] lg:mx-0">
        <Markdown body={body} boldTitle />
        {version && <p className="mt-6 text-small text-muted">Version {version}</p>}
      </article>
    </div>
  );
}

// CLAUDE.md 7: never serve final terms in production while a placeholder is empty.
function FinalTerms({ name, fill }: { name: string; fill: () => FilledTerms }) {
  const terms = useMemo(() => fill(), [fill]);
  if (terms.missing.length) {
    return (
      <section className="mx-auto max-w-[62ch] text-center">
        <h1>The {name} aren't available yet.</h1>
        <p className="mt-4 text-muted">Please check back soon, or contact us at founders@pacifyco.in.</p>
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

/** "← Back" to the page they came from (the footer link is on every page); home if they opened the
policy directly, e.g. from a bookmark (Reuben, 2026-11-13). */
function BackToPrevious() {
  const navigate = useNavigate();
  const goBack = useCallback(() => navigate(-1), [navigate]);
  const location = useLocation();
  const cameFromApp = location.key !== "default";
  useHeaderBack(cameFromApp ? { label: "Back", onBack: goBack } : { label: "Back", to: "/" });
  const content = (
    <>
      <ArrowLeft aria-hidden="true" size={18} strokeWidth={1.75} />
      Back
    </>
  );
  const className = "mb-4 inline-flex items-center gap-2 text-small text-coral-deep underline-offset-4 hover:underline";
  return cameFromApp ? (
    <button type="button" onClick={goBack} className={className}>
      {content}
    </button>
  ) : (
    <Link to="/" className={className}>
      {content}
    </Link>
  );
}

export function PrivacyPolicyPage() {
  return (
    <>
      <div className="mx-auto max-w-[72rem]">
        <BackToPrevious />
      </div>
      <LegalArticle body={PRIVACY_POLICY.body} version={PRIVACY_POLICY.meta.version} />
    </>
  );
}
