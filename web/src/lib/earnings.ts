// What a sitter earns (CLAUDE.md 6.2, 6.10), in words shared by her earnings page and the admin payouts list.

export type EarningKind = "booking" | "overtime" | "show_up_fee";

function duration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${rest} min`;
  const h = hours === 1 ? "1 hour" : `${hours} hours`;
  return rest === 0 ? h : `${h} ${rest} min`;
}

/** "Booking pay, 1 hour 30 min", "Overtime, 1 hour", "Show-up fee". */
export function earningLabel(earning: { kind: EarningKind; minutes: number | null }): string {
  if (earning.kind === "show_up_fee") return "Show-up fee";
  const what = earning.kind === "overtime" ? "Overtime" : "Booking pay";
  return earning.minutes ? `${what}, ${duration(earning.minutes)}` : what;
}
