import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { BackLink, Button } from "../components/ui";
import { ApiError, apiFetch } from "../lib/api";
import {
  END_HOURS,
  START_HOURS,
  WEEKDAYS,
  WEEKDAYS_SHORT,
  hoursLabel,
  shortHour,
  type WeekHours,
} from "../lib/times";

// A sitter's availability (CLAUDE.md 6.4; decided 2026-11-09): a week that repeats until she changes it,
// plus single days off. Families can book her inside these times, up to two weeks ahead. Kept compact so
// the whole week fits a phone screen.

type Availability = { week: WeekHours[]; days_off: string[] };
type Range = { start: number; end: number };
type Draft = Range[][]; // one list per weekday, Monday first

const KEY = ["sitter-availability"];

/** The times "+" adds, in order (Reuben, 2026-11-13): 9 am–1 pm, then 1–4, 4–7, 7–10 and 10 pm–12 am.
Each "+" adds the next one after her latest time on that day; after 10 pm–12 am there's nothing left to add,
so it never starts again at 9 am. She can still change any time with the selects. */
export const SLOTS: Range[] = [
  { start: 9, end: 13 },
  { start: 13, end: 16 },
  { start: 16, end: 19 },
  { start: 19, end: 22 },
  { start: 22, end: 24 },
];

/** The next time to add after a day's times, or null when the day is full up to midnight. */
export function nextSlot(ranges: Range[]): Range | null {
  if (!ranges.length) return SLOTS[0]!;
  const latest = Math.max(...ranges.map((range) => range.end));
  const slot = SLOTS.find((item) => item.start >= latest);
  if (slot) return slot;
  return latest < 24 ? { start: latest, end: 24 } : null;
}

function toDraft(week: WeekHours[]): Draft {
  const draft: Draft = WEEKDAYS.map(() => []);
  for (const hours of week) draft[hours.weekday]!.push({ start: hours.start_hour, end: hours.end_hour });
  return draft;
}

function toWeek(draft: Draft): WeekHours[] {
  return draft.flatMap((ranges, weekday) =>
    ranges.map((range) => ({ weekday, start_hour: range.start, end_hour: range.end })),
  );
}

/** Whether two weeks hold the same times, in any order. */
function sameWeek(a: WeekHours[], b: WeekHours[]): boolean {
  const key = (week: WeekHours[]) =>
    week
      .map((hours) => `${hours.weekday}:${hours.start_hour}-${hours.end_hour}`)
      .sort()
      .join(",");
  return key(a) === key(b);
}

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}

const hourSelect =
  "appearance-none rounded-pill border border-strong bg-surface-raised py-[6px] pr-[10px] pl-[10px] text-small text-ink";

function HourSelect({
  label,
  value,
  hours,
  onChange,
}: {
  label: string;
  value: number;
  hours: number[];
  onChange: (hour: number) => void;
}) {
  return (
    <select aria-label={label} value={value} onChange={(event) => onChange(Number(event.target.value))} className={hourSelect}>
      {hours.map((hour) => (
        <option key={hour} value={hour}>
          {shortHour(hour)}
        </option>
      ))}
    </select>
  );
}

function DayRow({
  weekday,
  ranges,
  onChange,
}: {
  weekday: number;
  ranges: Range[];
  onChange: (ranges: Range[]) => void;
}) {
  const day = WEEKDAYS[weekday]!;
  const free = ranges.length > 0;
  const update = (index: number, range: Range) => onChange(ranges.map((item, at) => (at === index ? range : item)));
  const next = nextSlot(ranges);

  return (
    <li className="flex items-start gap-2 border-t border-line py-2 first:border-t-0">
      <label className="flex w-[60px] shrink-0 cursor-pointer items-center gap-2 pt-[6px] text-ui text-ink">
        <input
          type="checkbox"
          checked={free}
          aria-label={`Free on ${day}s`}
          onChange={(event) => onChange(event.target.checked ? [{ start: 9, end: 13 }] : [])}
          className="size-[18px] accent-[var(--accent-coral)]"
        />
        <span aria-hidden="true">{WEEKDAYS_SHORT[weekday]}</span>
      </label>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        {!free && <span className="pt-[6px] text-small text-muted">Not free</span>}
        {ranges.map((range, index) => (
          <div key={index} className="flex items-center gap-1">
            <HourSelect
              label={`${day} from`}
              value={range.start}
              hours={START_HOURS}
              onChange={(start) => update(index, { ...range, start })}
            />
            <span aria-hidden="true" className="text-small text-muted">
              –
            </span>
            <HourSelect
              label={`${day} until`}
              value={range.end}
              hours={END_HOURS}
              onChange={(end) => update(index, { ...range, end })}
            />
            <button
              type="button"
              aria-label={`Remove ${day} ${hoursLabel(range.start, range.end)}`}
              onClick={() => onChange(ranges.filter((_, at) => at !== index))}
              className="flex size-[32px] shrink-0 items-center justify-center rounded-pill text-muted hover:text-ink"
            >
              <X aria-hidden="true" size={18} strokeWidth={1.75} />
            </button>
            {index === ranges.length - 1 && next && (
              <button
                type="button"
                aria-label={`Add a time on ${day}`}
                title="Add a time"
                onClick={() => onChange([...ranges, next])}
                className="flex size-[32px] shrink-0 items-center justify-center rounded-pill text-coral-deep hover:bg-surface-sunken"
              >
                <Plus aria-hidden="true" size={18} strokeWidth={1.75} />
              </button>
            )}
          </div>
        ))}
      </div>
    </li>
  );
}

function WeekCard({ saved }: { saved: WeekHours[] }) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<Draft>(() => toDraft(saved));
  const [problem, setProblem] = useState<string>();
  const changed = !sameWeek(toWeek(draft), saved);
  const save = useMutation({
    mutationFn: (week: WeekHours[]) =>
      apiFetch<Availability>("/sitter/availability/week", { method: "PUT", body: JSON.stringify({ hours: week }) }),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const week = toWeek(draft);
    if (week.some((hours) => hours.end_hour <= hours.start_hour)) {
      return setProblem("Each time must end after it starts.");
    }
    setProblem(undefined);
    save.mutate(week);
  }

  return (
    <section aria-labelledby="week-heading" className="rounded-lg bg-surface-raised p-4 shadow-soft sm:p-5">
      <form onSubmit={submit} noValidate>
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="week-heading" className="mr-auto text-ui font-semibold">
            Your week
          </h2>
        </div>
        <ul className="mt-2">
          {draft.map((ranges, weekday) => (
            <DayRow
              key={weekday}
              weekday={weekday}
              ranges={ranges}
              onChange={(next) => setDraft(draft.map((item, at) => (at === weekday ? next : item)))}
            />
          ))}
        </ul>
        {(problem || save.isError) && (
          <p role="alert" className="mt-2 text-small text-danger">
            {problem ?? errorText(save.error)}
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button type="submit" loading={save.isPending} disabled={!changed} fullWidthOnPhone={false}>
            Save my week
          </Button>
          {save.isSuccess && !changed && (
            <span role="status" className="text-small text-muted">
              Saved. It repeats every week until you change it.
            </span>
          )}
        </div>
      </form>
    </section>
  );
}

export function AvailabilityPage() {
  const availability = useQuery({ queryKey: KEY, queryFn: () => apiFetch<Availability>("/sitter/availability") });

  return (
    <section className="mx-auto flex max-w-[40rem] flex-col gap-4">
      <div className="flex items-start gap-4">
        <span className="mt-1 shrink-0">
          <BackLink to="/sitter" label="Home" />
        </span>
        <div className="min-w-0">
          <h1 className="text-h3">Your availability</h1>
          <p className="mt-1 text-small text-muted">
            Set your usual week once; it repeats every week. Families can book you inside these times, up to two
            weeks ahead.
          </p>
        </div>
      </div>
      {availability.isPending && <p className="text-muted">Loading…</p>}
      {availability.isError && (
        <p role="alert" className="text-danger">
          {errorText(availability.error)}
        </p>
      )}
      {/* Her usual week only: days off were taken out (Reuben, 2026-11-13). */}
      {availability.isSuccess && <WeekCard saved={availability.data.week} />}
    </section>
  );
}
