import { describe, expect, test } from "vitest";
import { formatBookingTime, formatDate, formatHours, formatTime, joinNames, plural } from "./format";

describe("format (always Asia/Kolkata)", () => {
  test("dates", () => {
    expect(formatDate(new Date("2026-10-12T06:00:00Z"))).toBe("12 Oct 2026");
    // 20:00 UTC is 1:30 am the next day in India
    expect(formatDate(new Date("2026-10-12T20:00:00Z"))).toBe("13 Oct 2026");
  });

  test("times are lowercase am/pm", () => {
    expect(formatTime(new Date("2026-10-12T13:00:00Z"))).toBe("6:30 pm");
    expect(formatTime(new Date("2026-10-12T18:30:00Z"))).toBe("12:00 am");
  });

  test("booking times", () => {
    expect(formatBookingTime(new Date("2026-10-10T04:30:00Z"), new Date("2026-10-10T07:30:00Z"))).toBe(
      "Sat, 10 Oct · 10:00 am – 1:00 pm",
    );
    expect(formatBookingTime(new Date("2026-10-10T14:30:00Z"), new Date("2026-10-10T19:30:00Z"))).toBe(
      "Sat, 10 Oct · 8:00 pm – Sun, 11 Oct · 1:00 am",
    );
  });

  test("hours from half-hour units", () => {
    expect(formatHours(0)).toBe("0 hours");
    expect(formatHours(1)).toBe("0.5 hours");
    expect(formatHours(2)).toBe("1 hour");
    expect(formatHours(5)).toBe("2.5 hours");
  });

  test("names without an Oxford comma", () => {
    expect(joinNames([])).toBe("");
    expect(joinNames(["Asha"])).toBe("Asha");
    expect(joinNames(["Asha", "Rohan"])).toBe("Asha and Rohan");
    expect(joinNames(["Asha", "Rohan", "Meera"])).toBe("Asha, Rohan and Meera");
  });

  test("plurals", () => {
    expect(plural(1, "review", "reviews")).toBe("1 review");
    expect(plural(3, "review", "reviews")).toBe("3 reviews");
  });
});
