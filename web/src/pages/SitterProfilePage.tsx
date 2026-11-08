import { useQuery } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { useParams } from "react-router";
import { BackLink, ButtonLink, Card, Chip, EmptyState, VerifiedChip } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { formatBookingTime, plural } from "../lib/format";
import { PLAN_LABELS, checksFor, distanceText, firstNameOf, type Plan, type SitterSummary } from "./FindSittersPage";

// One sitter's profile, for parents (CLAUDE.md 9). No price or pay (CLAUDE.md 6.1, 6.2); the plan's price
// is shown when the parent books.

type SitterDetail = SitterSummary & {
  bio: string | null;
  plan: Plan;
  free_times: { starts_at: string; ends_at: string }[];
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
            <ButtonLink to={code === "profile_unfinished" ? "/parent" : "/parent/sitters"} arrow>
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
          When {firstName} is free
        </h2>
        {sitter.free_times.length === 0 ? (
          <p className="mt-3 text-muted">No free times added yet.</p>
        ) : (
          <ul className="mt-3">
            {sitter.free_times.map((time) => (
              <li key={time.starts_at} className="border-t border-line py-3 first:border-t-0">
                {formatBookingTime(new Date(time.starts_at), new Date(time.ends_at))}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-5 rounded-lg bg-surface-sunken p-5 text-small text-ink">
          New to {firstName}? Start with a 1-hour booking while you're at home, to see how {firstName} gets on with
          your family. Booking from this page is coming soon.
        </p>
      </Card>
    </article>
  );
}
