import { expect, test } from "vitest";
import { laterTodayInIndia } from "./time";

test("stays on the same day in India", () => {
  const noonIst = Date.parse("2030-01-06T06:30:00Z");
  expect(laterTodayInIndia(60, noonIst).toISOString()).toBe("2030-01-06T07:30:00.000Z");
  const lateIst = Date.parse("2030-01-06T18:08:00Z"); // 11:38 pm in India
  expect(laterTodayInIndia(60, lateIst).toISOString()).toBe("2030-01-06T18:29:00.000Z"); // 11:59 pm
});
