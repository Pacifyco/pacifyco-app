import { Star } from "lucide-react";
import { plural } from "../../lib/format";
import { ButtonLink } from "./Button";
import { Card } from "./Card";
import { Chip, VerifiedChip, type VerifiedCheck } from "./Chip";

// design.md section 10. Answers the trust pillars in order: who, verified, experience, meet first.
// There is deliberately no rate or price prop: parents never see a sitter's rate (CLAUDE.md 6.2).
export type SitterCardProps = {
  name: string;
  firstName: string;
  photoUrl?: string;
  yearsExperience: number;
  area: string;
  ageGroups: string[];
  interests: string[];
  checks: VerifiedCheck[];
  rating: number | null;
  reviewCount: number;
  familiesServed: number;
  /** True once the pair has passed an introduction or had a booking. */
  unlocked: boolean;
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
  const { name, firstName, photoUrl, yearsExperience, area, ageGroups, interests, checks } = props;
  const { rating, reviewCount, familiesServed, unlocked, actionHref } = props;

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
          <h3 className="text-h3">{name}</h3>
          <p className="text-small text-muted">
            {plural(yearsExperience, "year's", "years'")} experience · {area}
          </p>
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

      {ageGroups.length + interests.length > 0 && (
        <ul aria-label="Ages and interests" className="flex flex-wrap gap-2">
          {ageGroups.map((group) => (
            <li key={`age-${group}`}>
              <Chip>{group}</Chip>
            </li>
          ))}
          {interests.map((interest) => (
            <li key={`interest-${interest}`}>
              <Chip tone="sunken">{interest}</Chip>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-col gap-1 text-small text-muted">
        <p className="flex items-center gap-1">
          {rating !== null && reviewCount > 0 ? (
            <>
              <Star aria-hidden="true" size={20} strokeWidth={1.75} className="text-coral-deep" />
              <span>
                <span className="text-ink">{rating.toFixed(1)}</span> · {plural(reviewCount, "review", "reviews")}
              </span>
            </>
          ) : (
            "New to Pacify"
          )}
        </p>
        {familiesServed > 0 && <p>Trusted by {plural(familiesServed, "Pacify family", "Pacify families")}</p>}
      </div>

      <ButtonLink to={actionHref} variant="primary">
        {unlocked ? "Choose a time" : `Meet ${firstName} first`}
      </ButtonLink>
    </Card>
  );
}
