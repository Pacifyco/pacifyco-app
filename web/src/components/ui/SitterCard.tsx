import { Star } from "lucide-react";
import { plural } from "../../lib/format";
import { ButtonLink } from "./Button";
import { Card } from "./Card";
import { VerifiedChip, type VerifiedCheck } from "./Chip";

// design.md section 10. Answers the trust pillars in order: who, verified, experience, try them first.
// Kept to photo, name, one line of facts, the checks and one action (UX review 2026-11-13).
// There is deliberately no rate or price prop: parents never see a sitter's rate (CLAUDE.md 6.2).
export type SitterCardProps = {
  name: string;
  firstName: string;
  photoUrl?: string;
  yearsExperience: number;
  /** Where she is, e.g. "2.4 km"; left out when unknown. */
  area?: string;
  /** e.g. "Ages 1½–5"; left out when she hasn't said. */
  ages?: string;
  checks: VerifiedCheck[];
  rating: number | null;
  reviewCount: number;
  familiesServed?: number;
  /** The plan she works, e.g. "Pause" (her level, CLAUDE.md 6.2). A name only, never a price. */
  plan?: string;
  actionHref: string;
};

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]!.toUpperCase())
    .join("");
}

export function SitterCard(props: SitterCardProps) {
  const { name, firstName, photoUrl, yearsExperience, area, ages, checks } = props;
  const { rating, reviewCount, familiesServed = 0, actionHref, plan } = props;
  const facts = [plural(yearsExperience, "yr", "yrs"), area, ages].filter(Boolean).join(" · ");

  return (
    <Card as="article" className="flex flex-col gap-4">
      <div className="flex items-center gap-4">
        {photoUrl ? (
          <img src={photoUrl} alt={name} className="size-[64px] shrink-0 rounded-pill object-cover" />
        ) : (
          <span
            aria-hidden="true"
            className="flex size-[64px] shrink-0 items-center justify-center rounded-pill bg-surface-tint text-h3 text-ink"
          >
            {initials(name)}
          </span>
        )}
        <div className="min-w-0">
          <h3 className="text-h3 break-words">{name}</h3>
          <p className="text-small text-muted">{facts}</p>
          {(plan || (rating !== null && reviewCount > 0)) && (
            <p className="mt-1 flex flex-wrap items-center gap-2 text-small text-muted">
              {plan && (
                <span className="rounded-pill border border-line px-3 py-px text-caption font-medium text-coral-deep">
                  <span className="sr-only">Works the </span>
                  {plan}
                  <span className="sr-only"> plan</span>
                </span>
              )}
              {rating !== null && reviewCount > 0 && (
                <span className="flex items-center gap-1">
                  <Star aria-hidden="true" size={18} strokeWidth={1.75} className="text-coral-deep" />
                  <span className="text-ink">{rating.toFixed(1)}</span> · {plural(reviewCount, "review", "reviews")}
                </span>
              )}
            </p>
          )}
        </div>
      </div>

      {checks.length > 0 && (
        <ul aria-label="Checks" className="flex flex-wrap gap-2">
          {checks.map((check) => (
            <li key={check}>
              <VerifiedChip check={check} />
            </li>
          ))}
        </ul>
      )}

      {familiesServed > 0 && (
        <p className="text-small text-muted">Trusted by {plural(familiesServed, "Pacifyco family", "Pacifyco families")}</p>
      )}

      <ButtonLink to={actionHref} variant="primary">
        See {firstName}'s profile
      </ButtonLink>
    </Card>
  );
}
