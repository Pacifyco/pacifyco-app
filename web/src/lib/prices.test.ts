import { describe, expect, test } from "vitest";
import { priceOnCard, priceOnProfile, rupees } from "./prices";

const PAUSE = { per_hour_paise: 49900, extra_child_paise: 0, one_child_only: true };
const UNWIND = { per_hour_paise: 69900, extra_child_paise: 15000, one_child_only: false };
const RECHARGE = { per_hour_paise: 89900, extra_child_paise: 0, one_child_only: false };

describe("prices parents see (CLAUDE.md 6.1, Reuben 2026-11-17)", () => {
  test("rupees, Indian grouping, no decimals when whole", () => {
    expect(rupees(269700)).toBe("₹2,697");
    expect(rupees(12345678)).toBe("₹1,23,456.78");
  });

  test("on the card", () => {
    expect(priceOnCard(PAUSE)).toBe("₹499/hour");
    expect(priceOnCard(UNWIND)).toBe("from ₹699/hour");
    expect(priceOnCard(RECHARGE)).toBe("₹899/hour");
  });

  test("on her profile", () => {
    expect(priceOnProfile(PAUSE)).toBe("₹499 an hour, for one child");
    expect(priceOnProfile(UNWIND)).toBe("₹699 an hour for one child, +₹150 an hour for each extra child");
    expect(priceOnProfile(RECHARGE)).toBe("₹899 an hour, for any number of children");
  });
});
