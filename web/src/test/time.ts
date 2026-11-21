// Times for tests that depend on "the day of the booking" in India (CLAUDE.md 6.7). A fixture that just
// adds an hour to now crosses midnight in India when CI runs late in the evening (IST is UTC+5:30, no DST).

const IST_OFFSET_MS = (5 * 60 + 30) * 60_000;
const DAY_MS = 24 * 60 * 60_000;

/** `minutes` from now, but never past 11:59 pm today in India (so still the same booking day). */
export function laterTodayInIndia(minutes: number, now = Date.now()): Date {
  const endOfIndiaDay = Math.floor((now + IST_OFFSET_MS) / DAY_MS) * DAY_MS + DAY_MS - IST_OFFSET_MS - 60_000;
  return new Date(Math.min(now + minutes * 60_000, endOfIndiaDay));
}
