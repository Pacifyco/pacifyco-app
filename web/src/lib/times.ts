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
