import { useQueries, useQuery } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { ButtonLink, Checkbox, EmptyState, Select, SitterCard, TextInput, ToggleChip } from "../components/ui";
import { cx } from "../components/ui/cx";
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
  /** One of her references has been approved by Pacifyco (references are optional). */
  references_checked: boolean;
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
export function checksFor(sitter: { first_aid: boolean; references_checked?: boolean }): VerifiedCheck[] {
  // References are optional (Reuben, 2026-11-13): "References checked" only when one has been approved.
  return [
    "id_police",
    ...(sitter.references_checked ? (["references"] as const) : []),
    ...(sitter.first_aid ? (["first_aid"] as const) : []),
  ];
}

/** The languages live sitters speak, from the unfiltered list, so every option finds someone. */
export function languagesOf(sitters: SitterSummary[]): string[] {
  const spoken = new Set(sitters.flatMap((sitter) => sitter.languages));
  return LANGUAGES.filter((language) => spoken.has(language));
}

// ---------- the search, kept in the address ----------

type Sort = "distance" | "rating" | "experience";
type Search = { day: string; part: PartOfDay | ""; languages: string[]; firstAid: boolean; sort: Sort };

function readSearch(params: URLSearchParams): Search {
  const part = params.get("time") ?? "";
  const sort = params.get("sort") ?? "distance";
  return {
    day: params.get("day") ?? "",
    part: PARTS_OF_DAY.some((item) => item.key === part) ? (part as PartOfDay) : "",
    languages: LANGUAGES.filter((language) => params.getAll("language").includes(language)),
    firstAid: params.get("firstaid") === "1",
    sort: ["distance", "rating", "experience"].includes(sort) ? (sort as Sort) : "distance",
  };
}

function toParams(search: Search): URLSearchParams {
  const params = new URLSearchParams();
  if (search.day) params.set("day", search.day);
  if (search.part && search.day) params.set("time", search.part);
  for (const language of search.languages) params.append("language", language);
  if (search.firstAid) params.set("firstaid", "1");
  if (search.sort !== "distance") params.set("sort", search.sort);
  return params;
}

function apiQuery(search: Search): string {
  const params = new URLSearchParams({ sort: search.sort });
  if (search.day) params.set("day", search.day);
  if (search.day && search.part) params.set("part", search.part);
  for (const language of search.languages) params.append("language", language);
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

const NONE: Search = { day: "", part: "", languages: [], firstAid: false, sort: "distance" };

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

const OTHER_DAY = "other";
const DATE_INPUT_ID = "find-a-sitter-date";

/** "Pick a day": Today, Tomorrow, the day after, or any other day in the next two weeks. A day picked
from the calendar shows in the dropdown itself (Reuben, 2026-11-13). */
function DayFilter({ search, set }: { search: Search; set: (patch: Partial<Search>) => void }) {
  const today = todayInKolkata();
  const quickDays = [today, addDays(today, 1), addDays(today, 2)];
  const [choosing, setChoosing] = useState(false);
  const custom = search.day && !quickDays.includes(search.day) ? search.day : "";
  useEffect(() => {
    if (!choosing) return;
    const input = document.getElementById(DATE_INPUT_ID) as HTMLInputElement | null;
    input?.focus();
    try {
      input?.showPicker?.(); // opens the calendar straight away where the browser allows it
    } catch {
      // Some browsers only open it on a click; the field is focused and ready.
    }
  }, [choosing]);

  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="w-[13rem]">
        <Select
          compact
          label="Pick a day"
          value={choosing ? OTHER_DAY : search.day}
          onChange={(event) => {
            const value = event.target.value;
            if (value === OTHER_DAY) return setChoosing(true);
            setChoosing(false);
            set(value ? { day: value } : { day: "", part: "" });
          }}
        >
          <option value="">Any day</option>
          <option value={quickDays[0]}>Today</option>
          <option value={quickDays[1]}>Tomorrow</option>
          <option value={quickDays[2]}>{dayLabel(quickDays[2]!)}</option>
          {custom && <option value={custom}>{dayLabel(custom)}</option>}
          <option value={OTHER_DAY}>Another date…</option>
        </Select>
      </div>
      {choosing && (
        <div className="w-[11rem]">
          <TextInput
            id={DATE_INPUT_ID}
            label="Choose a date"
            compact
            optional
            type="date"
            min={today}
            max={addDays(today, 13)}
            value={custom}
            onChange={(event) => {
              if (!event.target.value) return;
              set({ day: event.target.value });
              setChoosing(false);
            }}
          />
        </div>
      )}
    </div>
  );
}

function WhenFilter({ search, set }: { search: Search; set: (patch: Partial<Search>) => void }) {
  const today = todayInKolkata();
  return (
    <fieldset>
      <legend className="mb-2 text-small font-medium text-ink">When?</legend>
      <div className="flex flex-wrap gap-2">
        {PARTS_OF_DAY.map((part) => (
          <ToggleChip
            key={part.key}
            on={search.part === part.key && !!search.day}
            // A time of day needs a day: today, unless they've picked one.
            onToggle={() => set({ part: search.part === part.key ? "" : part.key, day: search.day || today })}
          >
            {part.label}
          </ToggleChip>
        ))}
      </div>
    </fieldset>
  );
}

/** A dropdown of languages to tick, several at once (Reuben, 2026-11-13). */
function LanguagesFilter({ search, set }: { search: Search; set: (patch: Partial<Search>) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    function onClick(event: MouseEvent) {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const chosen = search.languages;
  const summary = !chosen.length ? "Any" : chosen.length <= 2 ? chosen.join(", ") : `${chosen.length} languages`;
  function toggle(language: string) {
    set({
      languages: chosen.includes(language)
        ? chosen.filter((item) => item !== language)
        : LANGUAGES.filter((item) => item === language || chosen.includes(item)),
    });
  }

  return (
    <div ref={box} className="relative flex flex-col gap-1">
      <span id="languages-label" className="text-small font-medium text-ink">
        Languages
      </span>
      <button
        type="button"
        aria-haspopup="true"
        aria-expanded={open}
        aria-labelledby="languages-label languages-summary"
        onClick={() => setOpen(!open)}
        className={cx(
          "flex min-h-[44px] w-[13rem] items-center justify-between gap-2 rounded-pill border bg-surface-raised px-[14px] text-small text-ink",
          chosen.length ? "border-ink" : "border-strong",
        )}
      >
        <span id="languages-summary" className="truncate">
          {summary}
        </span>
        <ChevronDown aria-hidden="true" size={18} strokeWidth={1.75} />
      </button>
      {open && (
        <fieldset className="absolute top-full left-0 z-20 mt-2 flex w-[13rem] flex-col gap-3 rounded-md bg-surface-raised p-4 shadow-lift">
          <legend className="sr-only">Languages</legend>
          {LANGUAGES.map((language) => (
            <Checkbox
              key={language}
              label={<span className="text-small">{language}</span>}
              checked={chosen.includes(language)}
              onChange={() => toggle(language)}
            />
          ))}
          {chosen.length > 0 && (
            <button
              type="button"
              className="self-start text-small text-coral-deep underline-offset-4 hover:underline"
              onClick={() => set({ languages: [] })}
            >
              Any language
            </button>
          )}
        </fieldset>
      )}
    </div>
  );
}

/** Ways out of an empty result, each with how many sitters it would show. */
function Suggestions({ search, set }: { search: Search; set: (patch: Partial<Search>) => void }) {
  const options: { label: string; patch: Partial<Search> }[] = [];
  if (search.firstAid) options.push({ label: "Remove First aid", patch: { firstAid: false } });
  if (search.languages.length) options.push({ label: "Any language", patch: { languages: [] } });
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
          Ask the Pacifyco team to match you
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
                name={sitter.full_name ?? "Pacifyco sitter"}
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
      </div>

      {checklist.isPending ? (
        <p className="text-center text-muted">Loading…</p>
      ) : checklist.isSuccess && !checklist.data.finished ? (
        <FinishFirst checklist={checklist.data} />
      ) : (
        <>
          <section aria-label="Filters" className="flex flex-col gap-4 rounded-lg bg-surface-raised p-4 shadow-soft md:p-5">
            <DayFilter search={search} set={set} />
            <WhenFilter search={search} set={set} />
            <div className="flex flex-wrap items-end gap-3">
              <LanguagesFilter search={search} set={set} />
              <ToggleChip on={search.firstAid} onToggle={() => set({ firstAid: !search.firstAid })}>
                First aid
              </ToggleChip>
            </div>
          </section>
          <Results search={search} set={set} />
        </>
      )}
    </section>
  );
}
