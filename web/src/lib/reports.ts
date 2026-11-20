// Reports during a booking (CLAUDE.md 6.5): the parent wasn't home, or the sitter didn't come.

export type BookingReport = {
  id: string;
  kind: "parent_absent" | "sitter_no_show" | "only_man_home" | "child_under_age" | "sitter_unsafe";
  status: "open" | "confirmed" | "dismissed";
  reported_at: string;
  responded_at: string | null; // parent not home: a parent responded, so she waits
  can_leave_at: string | null; // parent not home: she may leave from then, if no one responds
  decision_note: string | null;
};

export const NO_SHOW_AFTER_MS = 30 * 60 * 1000; // a no-show can be reported from 30 minutes in
export const SHOW_UP_FEE_PER_HOUR_PAISE = 10_000; // ₹100 per booked hour
export const MAN_HOME_FEE_PAISE = 10_000; // a flat ₹100 when she declines because only a man is home

/** The booking is happening now: started and not yet ended. */
export function underWay(startsAt: string, endsAt: string, now: Date): boolean {
  return new Date(startsAt) <= now && now < new Date(endsAt);
}

/** A parent may report a no-show from 30 minutes after the start until the end. */
export function noShowReportable(startsAt: string, endsAt: string, now: Date): boolean {
  return now.getTime() >= new Date(startsAt).getTime() + NO_SHOW_AFTER_MS && now < new Date(endsAt);
}

/** "12 minutes", "1 minute", or null once it's passed. */
export function minutesLeft(until: string, now: Date): string | null {
  const ms = new Date(until).getTime() - now.getTime();
  if (ms <= 0) return null;
  const minutes = Math.ceil(ms / 60_000);
  return minutes === 1 ? "1 minute" : `${minutes} minutes`;
}
