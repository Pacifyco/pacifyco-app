// The neighbourhood each launch pin code covers (CLAUDE.md 1), so people see "Koramangala (560034)"
// rather than a bare number (UX review 2026-11-13). Names checked against OpenStreetMap; a pin code
// without a name here is shown on its own.
export const AREA_NAMES: Record<string, string> = {
  "560001": "MG Road",
  "560034": "Koramangala",
  "560038": "Indiranagar",
  "560078": "JP Nagar",
  "560084": "Lingarajapuram",
  "560095": "Koramangala 6th–8th Block",
  "560103": "Bellandur",
};

/** "MG Road (560001), Koramangala (560034)". */
export function areaList(pinCodes: string[]): string {
  return pinCodes.map((pin) => (AREA_NAMES[pin] ? `${AREA_NAMES[pin]} (${pin})` : pin)).join(", ");
}
