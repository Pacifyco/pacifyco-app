// The fixed lists a sitter picks from (UX review 2026-11-13; same lists as api/app/services/sitters.py),
// and the parts of the day parents filter by (api/app/services/availability.py PARTS_OF_DAY).

/** Pacifyco takes children from 18 months (CLAUDE.md 6.4), so there's no infant group. Ages in months. */
export const AGE_GROUPS = [
  { name: "Toddler", from: 18, to: 36, low: "1½", high: "3", label: "Toddler (18 months–3)" },
  { name: "Preschool", from: 36, to: 72, low: "3", high: "5", label: "Preschool (3–5)" },
  { name: "School age", from: 72, to: 156, low: "6", high: "12", label: "School age (6–12)" },
] as const;

export const LANGUAGES = ["English", "Kannada", "Hindi", "Tamil", "Malayalam", "Telugu"] as const;

/** ["Toddler", "Preschool"] → "Ages 1½–5". Older free-text entries are ignored. */
export function ageRange(groups: string[]): string | null {
  const chosen = AGE_GROUPS.filter((group) => groups.includes(group.name));
  if (!chosen.length) return null;
  return `Ages ${chosen[0]!.low}–${chosen[chosen.length - 1]!.high}`;
}

/** Whether a child of this age is in one of her age groups. */
export function suitsAge(groups: string[], ageInMonths: number): boolean {
  return AGE_GROUPS.some((group) => groups.includes(group.name) && ageInMonths >= group.from && ageInMonths < group.to);
}

export function monthsOld(dateOfBirth: string, today: Date = new Date()): number {
  const born = new Date(`${dateOfBirth}T00:00:00`);
  let months = (today.getFullYear() - born.getFullYear()) * 12 + today.getMonth() - born.getMonth();
  if (today.getDate() < born.getDate()) months -= 1;
  return months;
}

export type PartOfDay = "morning" | "afternoon" | "evening" | "night";

/** India time, whole hours. Night ends at midnight, the latest any plan runs (CLAUDE.md 6.1). */
export const PARTS_OF_DAY: { key: PartOfDay; label: string; start: number; end: number }[] = [
  { key: "morning", label: "Morning", start: 9, end: 13 },
  { key: "afternoon", label: "Afternoon", start: 13, end: 18 },
  { key: "evening", label: "Evening", start: 18, end: 22 },
  { key: "night", label: "Night", start: 22, end: 24 },
];
