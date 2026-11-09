import { useQuery } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { useParams } from "react-router";
import { BackLink, ButtonLink, Card, Chip, EmptyState, VerifiedChip } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { plural } from "../lib/format";
import { WEEKDAYS_SHORT, dayLabel, hoursLabel, type WeekHours } from "../lib/times";
import { PLAN_LABELS, checksFor, distanceText, firstNameOf, type SitterSummary } from "./FindSittersPage";

// One sitter's profile, for parents (CLAUDE.md 9). No price or pay (CLAUDE.md 6.1, 6.2); the plan's price
// is shown when the parent books.

type SitterDetail = SitterSummary & {
  bio: string | null;
  /** Her usual week, repeating (weekday 0 is Monday). */
  week: WeekHours[];
  /** Days she isn't free in the next two weeks. */
  days_off: string[];
  /** Recharge sitters only, with her consent (CLAUDE.md 6.2). */
  reference: { name: string; phone: string; relationship: string } | null;
};

function Facts({ sitter }: { sitter: SitterDetail }) {
  const facts = [
    sitter.years_experience !== null ? `${plural(sitter.years_experience, "year's", "years'")} experience` : null,
    distanceText(sitter.distance_km),
    sitter.languages.length ? `Speaks ${sitter.languages.join(", ")}` : null,
  ].filter(Boolean);
  return <p className="mt-2 text-muted">{facts.join(" · ")}</p>;
}

/** One line per day she's free: "Mon   9 am – 1 pm, 6 pm – 10 pm". */
function Week({ week }: { week: WeekHours[] }) {
  const days = WEEKDAYS_SHORT.map((name, weekday) => ({
    name,
    hours: week.filter((hours) => hours.weekday === weekday),
  })).filter((day) => day.hours.length > 0);
  if (days.length === 0) return <p className="mt-3 text-muted">No free times added yet.</p>;
  return (
    <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
      {days.map((day) => (
        <div key={day.name} className="contents">
          <dt className="text-ui text-ink">{day.name}</dt>
          <dd className="text-muted">{day.hours.map((hours) => hoursLabel(hours.start_hour, hours.end_hour)).join(", ")}</dd>
        </div>
      ))}
    </dl>
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
  return (
    <article className="mx-auto flex max-w-[48rem] flex-col gap-6">
      <BackLink to="/parent/sitters" label="Find a sitter" />
      <Card as="section" padding="roomy">
        {sitter.photo_url && (
          <img
            src={sitter.photo_url}
            alt={sitter.full_name ?? "Pacify sitter"}
            className="mb-5 size-[120px] rounded-pill object-cover"
          />
        )}
        <h1>{sitter.full_name ?? "Pacify sitter"}</h1>
        <Facts sitter={sitter} />
        <p className="mt-3 flex items-center gap-1 text-small text-muted">
          {sitter.avg_rating !== null && sitter.review_count > 0 ? (
            <>
              <Star aria-hidden="true" size={20} strokeWidth={1.75} className="text-coral-deep" />
              <span>
                <span className="text-ink">{sitter.avg_rating.toFixed(1)}</span> ·{" "}
                {plural(sitter.review_count, "review", "reviews")}
              </span>
            </>
          ) : (
            "New to Pacify"
          )}
        </p>
        <ul aria-label="Checks" className="mt-4 flex flex-wrap gap-2">
          {checksFor(sitter).map((check) => (
            <li key={check}>
              <VerifiedChip check={check} />
            </li>
          ))}
        </ul>
        {sitter.age_groups.length > 0 && (
          <ul aria-label="Ages" className="mt-3 flex flex-wrap gap-2">
            {sitter.age_groups.map((group) => (
              <li key={group}>
                <Chip>{group}</Chip>
              </li>
            ))}
          </ul>
        )}
        {sitter.bio && <p className="mt-5 whitespace-pre-line text-ink">{sitter.bio}</p>}
        <p className="mt-5 text-small text-muted">Works the {PLAN_LABELS[sitter.plan]} plan.</p>
      </Card>

      {sitter.reference && (
        <Card as="section" padding="roomy" aria-labelledby="reference-heading">
          <h2 id="reference-heading" className="text-h3">
            A reference for {firstName}
          </h2>
          <p className="mt-2 text-small text-muted">Checked by Pacify and shared with {firstName}'s permission.</p>
          <p className="mt-3 text-ink">
            {sitter.reference.name} · {sitter.reference.relationship}
          </p>
          <a href={`tel:${sitter.reference.phone}`} className="mt-1 inline-block">
            {sitter.reference.phone}
          </a>
        </Card>
      )}

      <Card as="section" padding="roomy" aria-labelledby="free-heading">
        <h2 id="free-heading" className="text-h3">
          When {firstName} is usually free
        </h2>
        <Week week={sitter.week} />
        {sitter.days_off.length > 0 && (
          <p className="mt-3 text-small text-muted">
            Not free on {sitter.days_off.map(dayLabel).join(", ")}.
          </p>
        )}
        <p className="mt-5 rounded-lg bg-surface-sunken p-5 text-small text-ink">
          New to {firstName}? Start with a 1-hour booking while you're at home, to see how {firstName} gets on with
          your family. Booking from this page is coming soon.
        </p>
      </Card>
    </article>
  );
}
