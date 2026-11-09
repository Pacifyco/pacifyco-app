// Picking times in Asia/Kolkata (CLAUDE.md 5: stored in UTC, shown in Asia/Kolkata). India has no
// daylight saving, so a fixed +05:30 offset is exact.

const OFFSET = "+05:30";
const HOUR_MS = 60 * 60 * 1000;

/** Today's date in Kolkata, "2026-11-08", for date inputs' `min`. */
export function todayInKolkata(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(now);
}

/** A date ("2026-11-10") and an hour (0–24; 24 is midnight at the end of that day) as a UTC ISO string. */
export function kolkataTime(date: string, hour: number): string {
  return new Date(new Date(`${date}T00:00:00${OFFSET}`).getTime() + hour * HOUR_MS).toISOString();
}

/** 9 → "9:00 am", 12 → "12:00 pm (noon)", 0 and 24 → "12:00 am (midnight)". */
export function hourLabel(hour: number): string {
  if (hour === 0 || hour === 24) return "12:00 am (midnight)";
  if (hour === 12) return "12:00 pm (noon)";
  return `${hour % 12}:00 ${hour < 12 ? "am" : "pm"}`;
}

export const START_HOURS = Array.from({ length: 24 }, (_, hour) => hour); // 0–23
export const END_HOURS = Array.from({ length: 24 }, (_, hour) => hour + 1); // 1–24

// ---------- a sitter's week (decided 2026-11-09: a week that repeats, plus days off) ----------

/** Weekday 0 is Monday, as the API sends it. */
export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const WEEKDAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export type WeekHours = { weekday: number; start_hour: number; end_hour: number };

/** 9 → "9 am", 12 → "12 pm", 0 and 24 → "12 am": short enough for a phone row. */
export function shortHour(hour: number): string {
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${twelve} ${hour % 24 < 12 ? "am" : "pm"}`;
}

/** "9 am – 1 pm". */
export function hoursLabel(start: number, end: number): string {
  return `${shortHour(start)} – ${shortHour(end)}`;
}

/** "2026-11-15" → "Sat 15 Nov". */
export function dayLabel(day: string): string {
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" })
    .format(new Date(`${day}T00:00:00Z`))
    .replace(",", "");
}
