// What parents pay, as they see it (CLAUDE.md 6.1). Money arrives from the API in paise. Parents see a
// sitter's rate, never her plan's name (Reuben, 2026-11-17), and never her pay.

/** A sitter's price per hour, from the API. */
export type Price = {
  per_hour_paise: number; // for one child
  extra_child_paise: number; // added per hour for each extra child; 0 means the same for any number
  one_child_only: boolean;
};

const RUPEES = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

/** ₹2,697 or ₹2,697.50: whole rupees without decimals. */
export function rupees(paise: number): string {
  const text = RUPEES.format(paise / 100);
  return paise % 100 === 0 ? text.replace(/\.00$/, "") : text;
}

/** On her card: "₹499/hour", or "from ₹699/hour" when extra children cost more. */
export function priceOnCard(price: Price): string {
  const perHour = `${rupees(price.per_hour_paise)}/hour`;
  return price.extra_child_paise > 0 ? `from ${perHour}` : perHour;
}

/** On her profile, in full. */
export function priceOnProfile(price: Price): string {
  const perHour = `${rupees(price.per_hour_paise)} an hour`;
  if (price.one_child_only) return `${perHour}, for one child`;
  if (price.extra_child_paise > 0) {
    return `${perHour} for one child, +${rupees(price.extra_child_paise)} an hour for each extra child`;
  }
  return `${perHour}, for any number of children`;
}
