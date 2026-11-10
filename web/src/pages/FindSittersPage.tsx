import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { ButtonLink, Checkbox, EmptyState, Select, SitterCard, TextInput } from "../components/ui";
import type { VerifiedCheck } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { todayInKolkata } from "../lib/times";

// Parents finding sitters (CLAUDE.md 9 "Search and filters"). Every live sitter is listed; parents filter
// by day and language, sort, and can ask for first-aid certified sitters only (Reuben, 2026-11-09). Kept
// compact to avoid scrolling. No prices or pay anywhere here (CLAUDE.md 6.1, 6.2).

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
  /** The plan she works (her level), shown as a label on her card. */
  plan: Plan;
};

export const PLAN_LABELS: Record<Plan, string> = {
  pause: "Pause · one child, until 6 pm",
  unwind: "Unwind · until 10:30 pm, bath time",
  recharge: "Recharge · until midnight, outings",
};

export const PLAN_NAMES: Record<Plan, string> = { pause: "Pause", unwind: "Unwind", recharge: "Recharge" };

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
  day: string;
  language: string;
  firstAid: boolean;
  sort: "distance" | "rating" | "experience";
};

const START: Search = { day: "", language: "", firstAid: false, sort: "distance" };

function queryString(search: Search): string {
  const params = new URLSearchParams({ sort: search.sort });
  if (search.day) params.set("day", search.day);
  if (search.language) params.set("language", search.language);
  if (search.firstAid) params.set("first_aid", "true");
  return params.toString();
}

function useSitters(query: string) {
  return useQuery({
    queryKey: ["sitter-search", query],
    queryFn: () => apiFetch<SitterSummary[]>(`/parent/sitters?${query}`),
  });
}

/** The languages live sitters speak, from the unfiltered list, so every option finds someone. */
export function languagesOf(sitters: SitterSummary[]): string[] {
  const byKey = new Map<string, string>();
  for (const sitter of sitters) {
    for (const language of sitter.languages) {
      const name = language.trim();
      if (name && !byKey.has(name.toLowerCase())) byKey.set(name.toLowerCase(), name);
    }
  }
  return [...byKey.values()].sort((a, b) => a.localeCompare(b));
}

function Results({ query }: { query: string }) {
  const results = useSitters(query);

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
    return <EmptyState message="No sitters match. Try another day or fewer filters." />;
  }
  return (
    <ul className="grid gap-4 md:grid-cols-2 md:gap-5" aria-label="Sitters">
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
            plan={PLAN_NAMES[sitter.plan]}
            actionHref={`/parent/sitters/${sitter.id}`}
          />
        </li>
      ))}
    </ul>
  );
}

export function FindSittersPage() {
  const [search, setSearch] = useState<Search>(START);
  const everyone = useSitters(queryString(START));
  const languages = useMemo(() => languagesOf(everyone.data ?? []), [everyone.data]);

  // Filters apply as soon as they change: no search button to reach.
  function set<K extends keyof Search>(field: K, value: Search[K]) {
    setSearch((current) => ({ ...current, [field]: value }));
  }

  return (
    <section className="mx-auto flex max-w-[72rem] flex-col gap-4">
      {/* The parent's home page: signed-in parents land here (AREA_PATH), so there's no back link. */}
      <div>
        <h1 className="text-h3">Find a sitter</h1>
        <p className="mt-1 text-small text-muted">
          Every sitter here is ID and police verified and referenced by Pacify. With someone new, start with a 1-hour
          booking while you're at home.
        </p>
      </div>

      {/* A card with tighter padding than Card's, so the filters take less room on a phone. */}
      <section
        aria-label="Filters"
        className="grid grid-cols-2 items-end gap-3 rounded-lg bg-surface-raised p-4 shadow-soft md:grid-cols-4 md:p-5"
      >
        <TextInput
          label="Day"
          type="date"
          optional
          compact
          min={todayInKolkata()}
          value={search.day}
          onChange={(event) => set("day", event.target.value)}
        />
        <Select compact label="Speaks" value={search.language} onChange={(event) => set("language", event.target.value)}>
          <option value="">Any</option>
          {languages.map((language) => (
            <option key={language} value={language}>
              {language}
            </option>
          ))}
        </Select>
        <Select
          compact
          label="Sort by"
          value={search.sort}
          onChange={(event) => set("sort", event.target.value as Search["sort"])}
        >
          <option value="distance">Nearest</option>
          <option value="rating">Highest rated</option>
          <option value="experience">Most experienced</option>
        </Select>
        <Checkbox
          className="pb-2"
          label={<span className="text-small">First-aid certified only</span>}
          checked={search.firstAid}
          onChange={(event) => set("firstAid", event.target.checked)}
        />
      </section>

      <Results query={queryString(search)} />
    </section>
  );
}
