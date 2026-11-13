import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { BackLink, Button, TextInput } from "../components/ui";
import { cx } from "../components/ui/cx";
import { ApiError, apiFetch } from "../lib/api";
import { PARTS_OF_DAY } from "../lib/sitterLists";
import {
  END_HOURS,
  START_HOURS,
  WEEKDAYS,
  WEEKDAYS_SHORT,
  dayLabel,
  hoursLabel,
  shortHour,
  todayInKolkata,
  type WeekHours,
} from "../lib/times";

// A sitter's availability (CLAUDE.md 6.4; decided 2026-11-09): a week that repeats until she changes it,
// plus single days off. Families can book her inside these times, up to two weeks ahead. Kept compact so
// the whole week fits a phone screen.

type Availability = { week: WeekHours[]; days_off: string[] };
type Range = { start: number; end: number };
type Draft = Range[][]; // one list per weekday, Monday first

const KEY = ["sitter-availability"];

/** Quick fills: the same parts of the day parents filter by (UX review 2026-11-13). */
export const PRESETS: { label: string; range: Range }[] = PARTS_OF_DAY.map((part) => ({
  label: part.key === "night" ? "Nights" : `${part.label}s`,
  range: { start: part.start, end: part.end },
}));

/** Adds a time to a day's times, joining any it overlaps or touches, so a quick fill never wipes
an earlier time (UX review 2026-11-13: "Afternoons" replaced Monday's morning). */
export function addRange(ranges: Range[], range: Range): Range[] {
  const sorted = [...ranges, range].sort((a, b) => a.start - b.start);
  const joined: Range[] = [];
  for (const next of sorted) {
    const last = joined.at(-1);
    if (last && next.start <= last.end) last.end = Math.max(last.end, next.end);
    else joined.push({ ...next });
  }
  return joined;
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
  const nextRange = (): Range => {
    const last = ranges.at(-1);
    if (!last || last.end >= 23) return { start: 9, end: 13 };
    return { start: last.end, end: Math.min(last.end + 3, 24) };
  };

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
            {index === ranges.length - 1 && (
              <button
                type="button"
                aria-label={`Add a time on ${day}`}
                title="Add a time"
                onClick={() => onChange([...ranges, nextRange()])}
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

  function fill(range: Range) {
    const ticked = draft.some((ranges) => ranges.length > 0);
    // With no day ticked yet, a quick fill sets Monday to Friday. It adds to each day's times.
    setDraft(
      draft.map((ranges, weekday) => ((ticked ? ranges.length > 0 : weekday < 5) ? addRange(ranges, range) : ranges)),
    );
  }

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
          <span className="text-small text-muted">Add to ticked days:</span>
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              onClick={() => fill(preset.range)}
              title={hoursLabel(preset.range.start, preset.range.end)}
              className="rounded-pill bg-surface-sunken px-3 py-1 text-small text-ink hover:bg-surface-tint"
            >
              {preset.label}
            </button>
          ))}
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

function DaysOffCard({ daysOff }: { daysOff: string[] }) {
  const queryClient = useQueryClient();
  const [day, setDay] = useState("");
  const [dayError, setDayError] = useState<string>();
  const add = useMutation({
    mutationFn: (value: string) =>
      apiFetch<Availability>("/sitter/availability/days-off", { method: "POST", body: JSON.stringify({ day: value }) }),
    onSuccess: (data) => {
      queryClient.setQueryData(KEY, data);
      setDay("");
    },
  });
  const remove = useMutation({
    mutationFn: (value: string) => apiFetch<void>(`/sitter/availability/days-off/${value}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!day) return setDayError("Please choose a day.");
    setDayError(undefined);
    add.mutate(day);
  }

  return (
    <section aria-labelledby="off-heading" className="rounded-lg bg-surface-raised p-4 shadow-soft sm:p-5">
      <h2 id="off-heading" className="text-ui font-semibold">
        Days off
      </h2>
      <p className="text-small text-muted">A day you can't work, whatever your week says.</p>
      <form onSubmit={submit} noValidate className="mt-2 flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <TextInput
            compact
            label="Day"
            type="date"
            min={todayInKolkata()}
            value={day}
            error={dayError}
            onChange={(event) => setDay(event.target.value)}
          />
        </div>
        <Button
          type="submit"
          variant="secondary"
          loading={add.isPending}
          fullWidthOnPhone={false}
          className={cx(dayError && "mb-[30px]")}
        >
          Mark day off
        </Button>
      </form>
      {(add.isError || remove.isError) && (
        <p role="alert" className="mt-2 text-small text-danger">
          {errorText(add.error ?? remove.error)}
        </p>
      )}
      {daysOff.length > 0 && (
        <ul aria-label="Your days off" className="mt-3 flex flex-wrap gap-2">
          {daysOff.map((value) => (
            <li key={value} className="flex items-center gap-1 rounded-pill bg-surface-sunken py-1 pr-1 pl-3 text-small">
              {dayLabel(value)}
              <button
                type="button"
                aria-label={`Remove day off ${dayLabel(value)}`}
                onClick={() => remove.mutate(value)}
                className="flex size-[24px] items-center justify-center rounded-pill text-muted hover:text-ink"
              >
                <X aria-hidden="true" size={14} strokeWidth={1.75} />
              </button>
            </li>
          ))}
        </ul>
      )}
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
      {availability.isSuccess && (
        <>
          <WeekCard saved={availability.data.week} />
          <DaysOffCard daysOff={availability.data.days_off} />
        </>
      )}
    </section>
  );
}
