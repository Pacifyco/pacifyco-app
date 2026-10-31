// Display formats from design.md section 2: "12 Oct 2026", "6:30 pm", "Sat, 11 Oct · 10:00 am – 1:00 pm".
// Times are stored in UTC and always shown in Asia/Kolkata (CLAUDE.md section 5).

const TIME_ZONE = "Asia/Kolkata";

function parts(date: Date, options: Intl.DateTimeFormatOptions): Record<string, string> {
  const result: Record<string, string> = {};
  for (const part of new Intl.DateTimeFormat("en-GB", { timeZone: TIME_ZONE, ...options }).formatToParts(date)) {
    result[part.type] = part.value;
  }
  return result;
}

/** "12 Oct 2026" */
export function formatDate(date: Date): string {
  const p = parts(date, { day: "numeric", month: "short", year: "numeric" });
  return `${p.day} ${p.month} ${p.year}`;
}

/** "Sat, 11 Oct" */
export function formatDay(date: Date): string {
  const p = parts(date, { weekday: "short", day: "numeric", month: "short" });
  return `${p.weekday}, ${p.day} ${p.month}`;
}

/** "6:30 pm" */
export function formatTime(date: Date): string {
  const p = parts(date, { hour: "numeric", minute: "2-digit", hour12: true });
  return `${p.hour}:${p.minute} ${p.dayPeriod.toLowerCase()}`;
}

/** "Sat, 11 Oct · 10:00 am – 1:00 pm"; the end day is added if the booking runs past midnight. */
export function formatBookingTime(start: Date, end: Date): string {
  const sameDay = formatDay(start) === formatDay(end);
  const endText = sameDay ? formatTime(end) : `${formatDay(end)} · ${formatTime(end)}`;
  return `${formatDay(start)} · ${formatTime(start)} – ${endText}`;
}

/** Half-hour units to words: 1 → "0.5 hours", 2 → "1 hour", 5 → "2.5 hours". */
export function formatHours(units: number): string {
  const hours = units / 2;
  return `${hours} ${hours === 1 ? "hour" : "hours"}`;
}

/** "Asha", "Asha and Rohan", "Asha, Rohan and Meera" (no Oxford comma, design.md section 2). */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}
