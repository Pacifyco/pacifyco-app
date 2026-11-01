import { formatDate, formatHours } from "../../lib/format";
import { Card } from "./Card";

// design.md section 10: child-hours left per child, nearest expiry and carried-forward hours.
// Amounts are half-hour units, as stored by the API (CLAUDE.md section 5).
export type ChildBalance = {
  childName: string;
  units: number;
  /** Expiry of the pack that runs out soonest, or null if only carried-forward hours are left. */
  nearestExpiry: Date | null;
  /** Part of `units` that was carried forward. Carried-forward hours never expire. */
  carriedForwardUnits: number;
};

export function HourBalance({ balances }: { balances: ChildBalance[] }) {
  return (
    <Card as="section" aria-labelledby="hour-balance-heading" className="flex flex-col gap-4">
      <h2 id="hour-balance-heading" className="text-h3">
        Your hours
      </h2>
      <ul className="flex flex-col divide-y divide-line">
        {balances.map((balance) => (
          <li key={balance.childName} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
            <div className="flex items-baseline justify-between gap-4">
              <span className="text-ui text-ink">{balance.childName}</span>
              <span className="text-body text-ink">{formatHours(balance.units)} left</span>
            </div>
            {balance.nearestExpiry && balance.units > balance.carriedForwardUnits && (
              <p className="text-small text-muted">Next expiry: {formatDate(balance.nearestExpiry)}</p>
            )}
            {balance.carriedForwardUnits > 0 && (
              <p className="text-small text-muted">
                Includes {formatHours(balance.carriedForwardUnits)} carried forward, which don't expire
              </p>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
