import { useQueries, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { ButtonLink, EmptyState, Select, SitterCard, TextInput, ToggleChip } from "../components/ui";
import type { VerifiedCheck } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import { plural } from "../lib/format";
import { LANGUAGES, PARTS_OF_DAY, ageRange, type PartOfDay } from "../lib/sitterLists";
import { dayLabel, todayInKolkata } from "../lib/times";
import { useChecklist, type ParentChecklist } from "./ProfileChecklist";

// Parents finding sitters (CLAUDE.md 9 "Search and filters"). Every live sitter is listed. Filters start
// with "When?" (a day, then a part of the day), then one row of chips; they live in the address, so
// Back, refresh and sharing keep them, and an empty result always offers a way out (UX review
// 2026-11-13). No prices or pay anywhere here (CLAUDE.md 6.1, 6.2).

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

/** What each plan means, in plain words (UX review 2026-11-13). */
export const PLAN_LABELS: Record<Plan, string> = {
  pause: "one child, until 6 pm",
  unwind: "any number of children, until 10:30 pm, bath time if you ask",
  recharge: "any number of children, until midnight, outings with your approval",
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

/** The languages live sitters speak, from the unfiltered list, so every option finds someone. */
export function languagesOf(sitters: SitterSummary[]): string[] {
  const spoken = new Set(sitters.flatMap((sitter) => sitter.languages));
  return LANGUAGES.filter((language) => spoken.has(language));
}

// ---------- the search, kept in the address ----------

type Sort = "distance" | "rating" | "experience";
type Search = { day: string; part: PartOfDay | ""; language: string; firstAid: boolean; sort: Sort };

function readSearch(params: URLSearchParams): Search {
  const part = params.get("time") ?? "";
  const sort = params.get("sort") ?? "distance";
  return {
    day: params.get("day") ?? "",
    part: PARTS_OF_DAY.some((item) => item.key === part) ? (part as PartOfDay) : "",
    language: params.get("language") ?? "",
    firstAid: params.get("firstaid") === "1",
    sort: ["distance", "rating", "experience"].includes(sort) ? (sort as Sort) : "distance",
  };
}

function toParams(search: Search): URLSearchParams {
  const params = new URLSearchParams();
  if (search.day) params.set("day", search.day);
  if (search.part && search.day) params.set("time", search.part);
  if (search.language) params.set("language", search.language);
  if (search.firstAid) params.set("firstaid", "1");
  if (search.sort !== "distance") params.set("sort", search.sort);
  return params;
}

function apiQuery(search: Search): string {
  const params = new URLSearchParams({ sort: search.sort });
  if (search.day) params.set("day", search.day);
  if (search.day && search.part) params.set("part", search.part);
  if (search.language) params.set("language", search.language);
  if (search.firstAid) params.set("first_aid", "true");
  return params.toString();
}

function sitterSearch(search: Search) {
  const query = apiQuery(search);
  return {
    queryKey: ["sitter-search", query],
    queryFn: () => apiFetch<SitterSummary[]>(`/parent/sitters?${query}`),
    // Keep showing the last results while a changed filter loads, so the page doesn't jump.
    placeholderData: (previous: SitterSummary[] | undefined) => previous,
  };
}

const NONE: Search = { day: "", part: "", language: "", firstAid: false, sort: "distance" };

/** "2026-11-14" plus days, as "2026-11-16". */
function addDays(day: string, days: number): string {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function whenText(search: Search, today: string): string {
  if (!search.day) return "";
  const day = search.day === today ? "today" : search.day === addDays(today, 1) ? "tomorrow" : dayLabel(search.day);
  const part = PARTS_OF_DAY.find((item) => item.key === search.part);
  return part ? `${day} ${part.label.toLowerCase()}` : day;
}

// ---------- the parts of the page ----------

function WhenFilter({ search, set }: { search: Search; set: (patch: Partial<Search>) => void }) {
  const today = todayInKolkata();
  const quickDays = [0, 1, 2, 3].map((offset) => addDays(today, offset));
  const pickedOther = search.day && !quickDays.includes(search.day);
  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-2 text-ui text-ink">When?</legend>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Day">
        {quickDays.map((day, index) => (
          <ToggleChip key={day} on={search.day === day} onToggle={() => set({ day: search.day === day ? "" : day })}>
            {index === 0 ? "Today" : index === 1 ? "Tomorrow" : dayLabel(day)}
          </ToggleChip>
        ))}
        <div className="w-[11rem]">
          <TextInput
            label="Pick a day"
            compact
            optional
            type="date"
            min={today}
            max={addDays(today, 13)}
            value={pickedOther ? search.day : ""}
            onChange={(event) => set({ day: event.target.value })}
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Time of day">
        {PARTS_OF_DAY.map((part) => (
          <ToggleChip
            key={part.key}
            on={search.part === part.key && !!search.day}
            // A time of day needs a day: today, unless they've picked one.
            onToggle={() =>
              set({ part: search.part === part.key ? "" : part.key, day: search.day || today })
            }
          >
            {part.label}
          </ToggleChip>
        ))}
      </div>
    </fieldset>
  );
}

function MoreFilters({ search, set }: { search: Search; set: (patch: Partial<Search>) => void }) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="More filters">
      <ToggleChip on={search.firstAid} onToggle={() => set({ firstAid: !search.firstAid })}>
        First aid
      </ToggleChip>
      {LANGUAGES.map((language) => (
        <ToggleChip
          key={language}
          on={search.language === language}
          onToggle={() => set({ language: search.language === language ? "" : language })}
        >
          {language}
        </ToggleChip>
      ))}
    </div>
  );
}

/** Ways out of an empty result, each with how many sitters it would show. */
function Suggestions({ search, set }: { search: Search; set: (patch: Partial<Search>) => void }) {
  const options: { label: string; patch: Partial<Search> }[] = [];
  if (search.firstAid) options.push({ label: "Remove First aid", patch: { firstAid: false } });
  if (search.language) options.push({ label: `Remove ${search.language}`, patch: { language: "" } });
  if (search.part) options.push({ label: "Any time that day", patch: { part: "" } });
  if (search.day) options.push({ label: "Any day", patch: { day: "", part: "" } });
  const counts = useQueries({ queries: options.map((option) => sitterSearch({ ...search, ...option.patch })) });
  const shown = options
    .map((option, index) => ({ ...option, count: counts[index]?.data?.length }))
    .filter((option) => option.count);
  return (
    <div className="flex flex-col items-center gap-4">
      {shown.length > 0 && (
        <ul className="flex flex-wrap justify-center gap-2">
          {shown.map((option) => (
            <li key={option.label}>
              <ToggleChip on={false} onToggle={() => set(option.patch)}>
                {option.label} · {plural(option.count!, "sitter", "sitters")}
              </ToggleChip>
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap justify-center gap-5 text-ui">
        <button type="button" className="text-coral-deep underline-offset-4 hover:underline" onClick={() => set(NONE)}>
          Clear all filters
        </button>
        <a href="mailto:founders@pacifyco.in?subject=Please%20help%20me%20find%20a%20sitter">
          Ask the Pacify team to match you
        </a>
      </div>
    </div>
  );
}

function Results({ search, set }: { search: Search; set: (patch: Partial<Search>) => void }) {
  const results = useQuery(sitterSearch(search));
  const filtered = apiQuery(search) !== apiQuery({ ...NONE, sort: search.sort });
  const when = whenText(search, todayInKolkata());

  if (results.isPending) return <p className="text-center text-muted">Finding sitters…</p>;
  if (results.isError && !results.data) {
    return (
      <p role="alert" className="text-center text-danger">
        {results.error instanceof ApiError ? results.error.message : "Something went wrong. Please try again."}
      </p>
    );
  }
  const count = results.data.length;
  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p aria-live="polite" className="text-ui text-ink">
          {plural(count, "sitter", "sitters")}
          {when ? ` free ${when}` : ""}
        </p>
        <div className="w-[12rem]">
          <Select
            compact
            label="Sort by"
            value={search.sort}
            onChange={(event) => set({ sort: event.target.value as Sort })}
          >
            <option value="distance">Nearest</option>
            <option value="rating">Highest rated</option>
            <option value="experience">Most experienced</option>
          </Select>
        </div>
      </div>
      {count === 0 ? (
        <EmptyState
          message={filtered ? "No sitters match all of these." : "No sitters are free near you yet."}
          action={<Suggestions search={search} set={set} />}
        />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2 md:gap-5" aria-label="Sitters">
          {results.data.map((sitter) => (
            <li key={sitter.id}>
              <SitterCard
                name={sitter.full_name ?? "Pacify sitter"}
                firstName={firstNameOf(sitter.full_name)}
                photoUrl={sitter.photo_url ?? undefined}
                yearsExperience={sitter.years_experience ?? 0}
                area={sitter.distance_km === null ? undefined : sitter.distance_km < 1 ? "<1 km" : `${sitter.distance_km.toFixed(1)} km`}
                ages={ageRange(sitter.age_groups) ?? undefined}
                checks={checksFor(sitter)}
                rating={sitter.avg_rating}
                reviewCount={sitter.review_count}
                plan={PLAN_NAMES[sitter.plan]}
                actionHref={`/parent/sitters/${sitter.id}`}
              />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** Until the profile is finished, no filters: just what's left and the way there. */
function FinishFirst({ checklist }: { checklist: ParentChecklist }) {
  const done = checklist.items.filter((item) => ["done", "waiting", "approved"].includes(item.status)).length;
  return (
    <EmptyState
      message={`Finish your profile first, then you can see sitters near you. ${done} of ${checklist.items.length} done.`}
      action={
        <ButtonLink to="/parent/profile" arrow>
          Finish your profile
        </ButtonLink>
      }
    />
  );
}

export function FindSittersPage() {
  const [params, setParams] = useSearchParams();
  const search = readSearch(params);
  const checklist = useChecklist<ParentChecklist>("parent");

  // Filters apply as soon as they change: no search button to reach.
  function set(patch: Partial<Search>) {
    setParams(toParams({ ...search, ...patch }), { replace: true });
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

      {checklist.isPending ? (
        <p className="text-center text-muted">Loading…</p>
      ) : checklist.isSuccess && !checklist.data.finished ? (
        <FinishFirst checklist={checklist.data} />
      ) : (
        <>
          <section aria-label="Filters" className="flex flex-col gap-4 rounded-lg bg-surface-raised p-4 shadow-soft md:p-5">
            <WhenFilter search={search} set={set} />
            <MoreFilters search={search} set={set} />
          </section>
          <Results search={search} set={set} />
        </>
      )}
    </section>
  );
}
