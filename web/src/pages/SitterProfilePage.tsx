import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, CircleCheck, Star } from "lucide-react";
import { useParams } from "react-router";
import { BackLink, ButtonLink, Card, Chip, EmptyState, VERIFIED_LABELS, type VerifiedCheck } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { plural } from "../lib/format";
import { AGE_GROUPS, PARTS_OF_DAY, ageRange, monthsOld, suitsAge } from "../lib/sitterLists";
import { WEEKDAYS_SHORT, dayLabel, type WeekHours } from "../lib/times";
import { PLAN_LABELS, PLAN_NAMES, checksFor, distanceText, firstNameOf, type SitterSummary } from "./FindSittersPage";

// One sitter's profile, for parents (CLAUDE.md 9): the moment a parent decides whether to trust someone.
// No price or pay (CLAUDE.md 6.1, 6.2); the plan's price is shown when the parent books. Never a
// referee's phone number (UX review 2026-11-13).

type SitterDetail = SitterSummary & {
  bio: string | null;
  /** Her usual week, repeating (weekday 0 is Monday). */
  week: WeekHours[];
  /** Days she isn't free in the next two weeks. */
  days_off: string[];
  /** Recharge sitters only, with her consent (CLAUDE.md 6.2). */
  reference: { name: string; relationship: string } | null;
  joined_at: string;
};

type Child = { id: string; name: string; date_of_birth: string };

// What each check means, for the expandable badges (only the checks Pacifyco does, CLAUDE.md 7).
const CHECK_DETAILS: Record<VerifiedCheck, string> = {
  id_police:
    "Pacifyco checked her government ID, a college or work ID and her police clearance certificate before her profile went live.",
  references: "Pacifyco spoke to two people who know her work before her profile went live.",
  psychology: "She took Pacifyco's psychology screening, and a Pacifyco admin reviewed her answers.",
  first_aid: "She has a first-aid certificate and sent it to Pacifyco with her application.",
};

function TrustBadge({ check }: { check: VerifiedCheck }) {
  return (
    <details className="group rounded-md border border-trust px-3 py-2 text-small">
      <summary className="flex cursor-pointer list-none items-center gap-2 font-medium text-trust">
        <BadgeCheck aria-hidden="true" size={20} strokeWidth={1.75} className="shrink-0" />
        {VERIFIED_LABELS[check]}
        <span className="text-caption text-muted group-open:hidden">What's this?</span>
      </summary>
      <p className="mt-2 text-muted">{CHECK_DETAILS[check]}</p>
    </details>
  );
}

function joinedText(at: string): string {
  const date = new Date(at);
  return `Joined ${date.toLocaleString("en-GB", { month: "short", year: "numeric", timeZone: "Asia/Kolkata" })}`;
}

/** Days × parts of the day, with "Not available" for days she isn't free (UX review 2026-11-13). */
function WeekGrid({ week }: { week: WeekHours[] }) {
  function free(weekday: number, start: number, end: number) {
    return week.some((hours) => hours.weekday === weekday && hours.start_hour < end && hours.end_hour > start);
  }
  if (week.length === 0) return <p className="mt-3 text-muted">No free times added yet.</p>;
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full min-w-[22rem] border-collapse text-small">
        <thead>
          <tr>
            <th scope="col" className="sr-only">
              Day
            </th>
            {PARTS_OF_DAY.map((part) => (
              <th key={part.key} scope="col" className="px-1 pb-2 text-center font-medium text-muted">
                {part.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {WEEKDAYS_SHORT.map((name, weekday) => {
            const anyFree = PARTS_OF_DAY.some((part) => free(weekday, part.start, part.end));
            return (
              <tr key={name} className="border-t border-line">
                <th scope="row" className="py-2 pr-3 text-left font-medium text-ink">
                  {name}
                </th>
                {anyFree ? (
                  PARTS_OF_DAY.map((part) =>
                    free(weekday, part.start, part.end) ? (
                      <td key={part.key} className="py-2 text-center text-trust">
                        <CircleCheck aria-hidden="true" size={18} strokeWidth={1.75} className="mx-auto" />
                        <span className="sr-only">Free</span>
                      </td>
                    ) : (
                      <td key={part.key} className="py-2 text-center text-muted">
                        <span aria-hidden="true">–</span>
                        <span className="sr-only">Not free</span>
                      </td>
                    ),
                  )
                ) : (
                  <td colSpan={PARTS_OF_DAY.length} className="py-2 text-center text-muted">
                    Not available
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** "Suits Diya (4)": her age groups against the family's children. */
function SuitsYourChildren({ groups }: { groups: string[] }) {
  const children = useQuery({ queryKey: ["children"], queryFn: () => apiFetch<Child[]>("/parent/children") });
  const suited = (children.data ?? []).filter((child) => suitsAge(groups, monthsOld(child.date_of_birth)));
  if (!suited.length) return null;
  return (
    <p className="mt-3 flex items-center gap-2 text-small text-trust">
      <CircleCheck aria-hidden="true" size={18} strokeWidth={1.75} />
      Suits{" "}
      {suited.map((child) => `${child.name} (${Math.floor(monthsOld(child.date_of_birth) / 12)})`).join(", ")}
    </p>
  );
}

export function SitterProfilePage() {
  const { sitterId = "" } = useParams();
  const profile = useQuery({
    queryKey: ["sitter-profile", sitterId],
    queryFn: () => apiFetch<SitterDetail>(`/parent/sitters/${sitterId}`),
  });

  if (profile.isPending) return <p className="text-center text-muted">Loading…</p>;
  if (profile.isError) {
    const code = profile.error instanceof ApiError ? profile.error.code : null;
    return (
      <section className="mx-auto max-w-[40rem]">
        <EmptyState
          message={
            code === "profile_unfinished"
              ? "Finish your profile first, then you can see sitters near you."
              : code === "not_found"
                ? "This sitter isn't available right now."
                : "Something went wrong. Please try again."
          }
          action={
            <ButtonLink to={code === "profile_unfinished" ? "/parent/profile" : "/parent/sitters"} arrow>
              {code === "profile_unfinished" ? "Finish your profile" : "Find a sitter"}
            </ButtonLink>
          }
        />
      </section>
    );
  }

  const sitter = profile.data;
  const firstName = firstNameOf(sitter.full_name);
  const ages = ageRange(sitter.age_groups);
  const facts = [
    sitter.years_experience !== null ? `${plural(sitter.years_experience, "year's", "years'")} experience` : null,
    distanceText(sitter.distance_km),
    joinedText(sitter.joined_at),
  ].filter(Boolean);
  return (
    <article className="mx-auto flex max-w-[56rem] flex-col gap-6 [overflow-wrap:anywhere]">
      <BackLink to="/parent/sitters" label="Find a sitter" />
      <Card as="section" padding="roomy" className="md:grid md:grid-cols-[10rem_1fr] md:gap-7">
        {sitter.photo_url ? (
          <img
            src={sitter.photo_url}
            alt={sitter.full_name ?? "Pacifyco sitter"}
            className="mb-5 size-[120px] rounded-pill object-cover md:size-[160px]"
          />
        ) : (
          <span aria-hidden="true" className="hidden md:block" />
        )}
        <div className="min-w-0">
          <h1 className="break-words">{sitter.full_name ?? "Pacifyco sitter"}</h1>
          <p className="mt-2 text-muted">{facts.join(" · ")}</p>
          {sitter.avg_rating !== null && sitter.review_count > 0 && (
            <p className="mt-2 flex items-center gap-1 text-small text-muted">
              <Star aria-hidden="true" size={20} strokeWidth={1.75} className="text-coral-deep" />
              <span className="text-ink">{sitter.avg_rating.toFixed(1)}</span> ·{" "}
              {plural(sitter.review_count, "review", "reviews")}
            </p>
          )}
          <ul aria-label="Checks" className="mt-4 flex flex-col gap-2 sm:max-w-[28rem]">
            {checksFor(sitter).map((check) => (
              <li key={check}>
                <TrustBadge check={check} />
              </li>
            ))}
          </ul>
        </div>
      </Card>

      <Card as="section" padding="roomy" aria-labelledby="about-heading">
        <h2 id="about-heading" className="text-h3">
          About {firstName}
        </h2>
        {sitter.bio && <p className="mt-3 whitespace-pre-line text-ink">{sitter.bio}</p>}
        {ages && (
          <>
            <p className="mt-4 text-ui text-ink">Comfortable with {ages.toLowerCase()}</p>
            <ul aria-label="Ages" className="mt-2 flex flex-wrap gap-2">
              {AGE_GROUPS.filter((group) => sitter.age_groups.includes(group.name)).map((group) => (
                <li key={group.name}>
                  <Chip tone="outline">{group.label}</Chip>
                </li>
              ))}
            </ul>
          </>
        )}
        <SuitsYourChildren groups={sitter.age_groups} />
        {sitter.languages.length > 0 && (
          <>
            <p className="mt-4 text-ui text-ink">Speaks</p>
            <ul aria-label="Languages" className="mt-2 flex flex-wrap gap-2">
              {sitter.languages.map((language) => (
                <li key={language}>
                  <Chip tone="outline">{language}</Chip>
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="mt-5 text-small text-muted">
          {firstName} works the {PLAN_NAMES[sitter.plan]} plan: {PLAN_LABELS[sitter.plan]}.
        </p>
      </Card>

      {sitter.reference && (
        <Card as="section" padding="roomy" aria-labelledby="reference-heading">
          <h2 id="reference-heading" className="text-h3">
            A reference for {firstName}
          </h2>
          <figure className="mt-3 border-l-4 border-coral pl-4">
            <figcaption className="text-ink">
              {sitter.reference.name} · {sitter.reference.relationship}
            </figcaption>
          </figure>
          <p className="mt-3 text-small text-muted">Checked by Pacifyco and shared with {firstName}'s permission.</p>
        </Card>
      )}

      <Card as="section" padding="roomy" aria-labelledby="free-heading">
        <h2 id="free-heading" className="text-h3">
          When {firstName} is usually free
        </h2>
        <WeekGrid week={sitter.week} />
        {sitter.days_off.length > 0 && (
          <p className="mt-3 text-small text-muted">Not free on {sitter.days_off.map(dayLabel).join(", ")}.</p>
        )}
        <p className="mt-5 rounded-lg bg-surface-sunken p-5 text-small text-ink">
          New to {firstName}? Start with a 1-hour booking while you're at home, to see how {firstName} gets on with
          your family. Booking from this page is coming soon.
        </p>
      </Card>
    </article>
  );
}
