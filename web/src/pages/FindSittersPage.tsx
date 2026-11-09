import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { BackLink, Button, ButtonLink, Card, Checkbox, EmptyState, Select, SitterCard, TextInput } from "../components/ui";
import type { VerifiedCheck } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { END_HOURS, START_HOURS, hourLabel, kolkataTime, todayInKolkata } from "../lib/times";

// Parents finding sitters (CLAUDE.md 9 "Search and filters"). Only live sitters of the chosen plan's
// level come back. No prices or pay anywhere here (CLAUDE.md 6.1, 6.2).

export type Plan = "pause" | "unwind" | "recharge";

export type SitterSummary = {
  id: string;
  full_name: string | null;
  years_experience: number | null;
  age_groups: string[];
  languages: string[];
  first_aid: boolean;
  avg_rating: number | null;
  review_count: number;
  distance_km: number | null;
  /** Short-lived signed link to her photo; null shows initials. */
  photo_url: string | null;
};

export const PLAN_LABELS: Record<Plan, string> = {
  pause: "Pause · one child, until 6 pm",
  unwind: "Unwind · until 10:30 pm, bath time",
  recharge: "Recharge · until midnight, outings",
};

export function firstNameOf(name: string | null): string {
  return name?.trim().split(/\s+/)[0] || "this sitter";
}

export function distanceText(km: number | null): string | undefined {
  if (km === null) return undefined;
  return km < 1 ? "under 1 km away" : `${km.toFixed(1)} km away`;
}

/** Checks every live sitter has passed (CLAUDE.md 7). The psychology chip waits for the real questions. */
export function checksFor(sitter: { first_aid: boolean }): VerifiedCheck[] {
  return sitter.first_aid ? ["id_police", "references", "first_aid"] : ["id_police", "references"];
}

type Search = {
  plan: Plan;
  date: string;
  from: number;
  until: number;
  language: string;
  minYears: string;
  minRating: string;
  firstAid: boolean;
  sort: "distance" | "rating" | "experience";
};

const START: Search = {
  plan: "pause",
  date: "",
  from: 18,
  until: 21,
  language: "",
  minYears: "",
  minRating: "",
  firstAid: false,
  sort: "distance",
};

function queryString(search: Search): string {
  const params = new URLSearchParams({ plan: search.plan, sort: search.sort });
  if (search.date) {
    params.set("starts_at", kolkataTime(search.date, search.from));
    params.set("ends_at", kolkataTime(search.date, search.until));
  }
  if (search.language.trim()) params.set("language", search.language.trim());
  if (search.minYears) params.set("min_years", search.minYears);
  if (search.minRating) params.set("min_rating", search.minRating);
  if (search.firstAid) params.set("first_aid", "true");
  return params.toString();
}

function Results({ query }: { query: string }) {
  const results = useQuery({
    queryKey: ["sitter-search", query],
    queryFn: () => apiFetch<SitterSummary[]>(`/parent/sitters?${query}`),
  });

  if (results.isPending) return <p className="text-center text-muted">Finding sitters…</p>;
  if (results.isError) {
    if (results.error instanceof ApiError && results.error.code === "profile_unfinished") {
      return (
        <EmptyState
          message="Finish your profile first, then you can see sitters near you."
          action={
            <ButtonLink to="/parent/profile" arrow>
              Finish your profile
            </ButtonLink>
          }
        />
      );
    }
    return (
      <p role="alert" className="text-center text-danger">
        {results.error instanceof ApiError ? results.error.message : "Something went wrong. Please try again."}
      </p>
    );
  }
  if (results.data.length === 0) {
    return <EmptyState message="No sitters match yet. Try another time, another plan or fewer filters." />;
  }
  return (
    <ul className="grid gap-5 md:grid-cols-2" aria-label="Sitters">
      {results.data.map((sitter) => (
        <li key={sitter.id}>
          <SitterCard
            name={sitter.full_name ?? "Pacify sitter"}
            firstName={firstNameOf(sitter.full_name)}
            photoUrl={sitter.photo_url ?? undefined}
            yearsExperience={sitter.years_experience ?? 0}
            area={distanceText(sitter.distance_km)}
            ageGroups={sitter.age_groups}
            interests={sitter.languages}
            checks={checksFor(sitter)}
            rating={sitter.avg_rating}
            reviewCount={sitter.review_count}
            actionHref={`/parent/sitters/${sitter.id}`}
          />
        </li>
      ))}
    </ul>
  );
}

export function FindSittersPage() {
  const [form, setForm] = useState<Search>(START);
  const [applied, setApplied] = useState(() => queryString(START));
  const [timeError, setTimeError] = useState<string>();

  function set<K extends keyof Search>(field: K, value: Search[K]) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (form.date && form.until <= form.from) return setTimeError("The end time must be after the start time.");
    setTimeError(undefined);
    setApplied(queryString(form));
  }

  return (
    <section className="mx-auto flex max-w-[72rem] flex-col gap-6">
      <BackLink to="/parent" label="Home" />
      <div className="text-center">
        <h1>Find a sitter</h1>
        <p className="mx-auto mt-4 max-w-[62ch] text-muted">
          Every sitter here is ID and police verified and referenced by Pacify. With someone new, start with a 1-hour
          booking while you're at home.
        </p>
      </div>

      <Card as="section" padding="roomy" aria-label="Search">
        <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
          <div className="grid gap-5 md:grid-cols-2">
            <Select label="Plan" value={form.plan} onChange={(event) => set("plan", event.target.value as Plan)}>
              {(Object.keys(PLAN_LABELS) as Plan[]).map((plan) => (
                <option key={plan} value={plan}>
                  {PLAN_LABELS[plan]}
                </option>
              ))}
            </Select>
            <TextInput
              label="Day"
              type="date"
              optional
              min={todayInKolkata()}
              value={form.date}
              onChange={(event) => set("date", event.target.value)}
            />
          </div>
          {form.date && (
            <div className="grid gap-5 md:grid-cols-2">
              <Select label="From" value={form.from} onChange={(event) => set("from", Number(event.target.value))}>
                {START_HOURS.map((hour) => (
                  <option key={hour} value={hour}>
                    {hourLabel(hour)}
                  </option>
                ))}
              </Select>
              <Select
                label="Until"
                value={form.until}
                error={timeError}
                onChange={(event) => set("until", Number(event.target.value))}
              >
                {END_HOURS.map((hour) => (
                  <option key={hour} value={hour}>
                    {hourLabel(hour)}
                  </option>
                ))}
              </Select>
            </div>
          )}
          <div className="grid gap-5 md:grid-cols-3">
            <TextInput
              label="Speaks"
              optional
              placeholder="e.g. Kannada"
              maxLength={40}
              value={form.language}
              onChange={(event) => set("language", event.target.value)}
            />
            <Select label="Experience" value={form.minYears} onChange={(event) => set("minYears", event.target.value)}>
              <option value="">Any</option>
              <option value="1">1 year or more</option>
              <option value="3">3 years or more</option>
              <option value="5">5 years or more</option>
            </Select>
            <Select label="Rating" value={form.minRating} onChange={(event) => set("minRating", event.target.value)}>
              <option value="">Any</option>
              <option value="4">4 stars or more</option>
              <option value="4.5">4.5 stars or more</option>
            </Select>
          </div>
          <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
            <Checkbox
              label="First-aid certified only"
              checked={form.firstAid}
              onChange={(event) => set("firstAid", event.target.checked)}
            />
            <Select
              label="Sort by"
              value={form.sort}
              onChange={(event) => set("sort", event.target.value as Search["sort"])}
            >
              <option value="distance">Nearest</option>
              <option value="rating">Highest rated</option>
              <option value="experience">Most experienced</option>
            </Select>
          </div>
          <Button type="submit" arrow fullWidthOnPhone={false} className="self-start">
            Show sitters
          </Button>
        </form>
      </Card>

      <Results query={applied} />
    </section>
  );
}
