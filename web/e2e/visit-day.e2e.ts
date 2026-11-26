import { execFileSync } from "node:child_process";
import { expect, test, type Page } from "@playwright/test";
import { apiEnv, python } from "./env";
import { signIn, type Person } from "./people";

// The day of a booking and after it, end to end (CLAUDE.md 6.7, 6.8, 6.10, 6.11): the parent reads out the
// check-in code, the sitter checks in, the parent asks for overtime and she accepts, she checks out with the
// check-out code, her pay is due, an admin pays it, and the parent reviews a sitter.
//
// A booking for today can't be made in the app (it must start 6 hours ahead), so this uses the staging seed
// (api/app/services/staging_seed.py) the way Reuben does: api/e2e_people.py makes a ready parent and sitter,
// then seeds bookings for them, one of them today. It runs after onboarding.e2e.ts (files run in name order,
// one at a time), whose checks expect a database without the seed's people.

let parent: Person;
let sitter: Person;
let admin: Person;

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ browser }) => {
  parent = await signIn(browser, "day-parent");
  // Check-in records her location (6.7): allowed in her browser, somewhere in Koramangala.
  sitter = await signIn(browser, "day-sitter", {
    permissions: ["geolocation"],
    geolocation: { latitude: 12.9352, longitude: 77.6245 },
  });
  admin = await signIn(browser, "day-admin");
  const env = { ...process.env, ...apiEnv };
  execFileSync(python, ["-m", "app.cli", "create-admin", "--email", admin.email, "--name", "Day Admin", "--user-id", admin.id], {
    cwd: "../api",
    env,
  });
  execFileSync(
    python,
    ["e2e_people.py", "--parent-id", parent.id, "--parent-email", parent.email, "--sitter-id", sitter.id, "--sitter-email", sitter.email],
    { cwd: "../api", env },
  );
});

/** The 4-digit code on the parent's booking page. */
async function codeOn(page: Page, label: "check-in" | "check-out"): Promise<string> {
  const card = page.locator("section").filter({ has: page.getByRole("heading", { name: `Your ${label} code` }) });
  const code = card.getByText(/^\d{4}$/);
  await expect(code).toBeVisible();
  return (await code.textContent())!.trim();
}

async function openTodaysBooking(person: Person) {
  const page = person.page;
  if (person === parent) {
    await page.goto("/parent/bookings");
    await page.getByRole("tabpanel").getByRole("link").filter({ hasText: "Rekha with Mira" }).click();
    await expect(page.getByRole("heading", { name: "Your booking with Rekha" })).toBeVisible();
  } else {
    await page.goto("/sitter/bookings");
    await page.getByRole("tabpanel").getByRole("link").filter({ hasText: "at Nisha's home" }).click();
    await expect(page.getByRole("heading", { name: "Nisha's family" })).toBeVisible();
  }
}

let checkInCode = "";

test("the parent sees today's check-in code, and no check-out code yet", async () => {
  await openTodaysBooking(parent);
  checkInCode = await codeOn(parent.page, "check-in");
  await expect(parent.page.getByRole("heading", { name: "Your check-out code" })).toHaveCount(0);
});

test("a wrong code is refused; the right one checks her in", async () => {
  await openTodaysBooking(sitter);
  const page = sitter.page;
  const wrong = checkInCode === "0000" ? "1111" : "0000";
  await page.getByLabel("Check-in code").fill(wrong);
  await page.getByRole("button", { name: "Check in", exact: true }).click();
  await expect(page.getByText("That code's wrong. 4 tries left.")).toBeVisible();
  await page.getByLabel("Check-in code").fill(checkInCode);
  await page.getByRole("button", { name: "Check in", exact: true }).click();
  await expect(page.getByLabel("Check-out code")).toBeVisible();
});

test("the parent asks for an hour of overtime and the sitter accepts", async () => {
  const page = parent.page;
  await page.reload();
  await page.getByRole("button", { name: "Request overtime" }).click();
  await page.getByLabel("How many more hours?").selectOption("1");
  await page.getByRole("button", { name: "Send the request" }).click();
  await expect(page.getByText("Waiting for Rekha to answer: 1 more hour.")).toBeVisible();

  await sitter.page.reload();
  await expect(sitter.page.getByText(/The family has asked if you can stay 1 more hour\./)).toBeVisible();
  await sitter.page.getByRole("button", { name: "Accept", exact: true }).click();
  await expect(sitter.page.getByText(/The family has asked if you can stay/)).toHaveCount(0);

  await page.reload();
  await expect(page.getByText("Rekha can stay 1 more hour.")).toBeVisible();
});

test("the sitter checks out with the parent's check-out code", async () => {
  await parent.page.reload();
  const code = await codeOn(parent.page, "check-out");
  const page = sitter.page;
  await page.getByLabel("Check-out code").fill(code);
  await page.getByRole("button", { name: "Check out", exact: true }).click();
  await expect(page.getByLabel("Check-out code")).toHaveCount(0);

  // The codes go once it's checked out.
  await parent.page.reload();
  await expect(parent.page.getByRole("heading", { name: /Your check-(in|out) code/ })).toHaveCount(0);
});

test("her pay is due; an admin pays it and she sees it paid", async () => {
  await sitter.page.goto("/sitter/earnings");
  const totals = sitter.page.getByRole("region", { name: "Your totals" });
  await expect(totals).toContainText("Due to you");
  await expect(sitter.page.locator("body")).not.toContainText(/Pause|Unwind|Recharge|₹499/);

  const page = admin.page;
  await page.goto("/admin/payouts");
  const card = page.getByRole("listitem").filter({ has: page.getByText("Rekha Das", { exact: true }) });
  await expect(card.getByText("UPI: rekha.e2e@upi")).toBeVisible();
  await card.getByRole("button", { name: "Mark paid" }).click();
  await card.getByLabel(/Transfer reference/).fill("UTRE2E123456");
  // Her pay is to the minute from check-in (6.2), so the amount can have paise.
  await card.getByRole("button", { name: /^Mark ₹[\d,.]+ paid$/ }).click();
  await expect(page.getByText("Rekha Das", { exact: true })).toHaveCount(0);

  await sitter.page.reload();
  await expect(sitter.page.getByRole("region", { name: "Payments to you" })).toContainText("UTRE2E123456");
});

test("the parent reviews the sitter from an earlier booking", async () => {
  const page = parent.page;
  await page.goto("/parent/bookings?show=past");
  await page.getByRole("tabpanel").getByRole("link").filter({ hasText: "Ananya with Mira" }).click();
  const form = page.getByRole("region", { name: "Leave a review" });
  // Tap the fifth star (the radio inside it is visually hidden).
  const five = form.getByRole("radio", { name: "5 stars" });
  await five.locator("..").click();
  await expect(five).toBeChecked();
  await form.getByLabel(/A few words/).fill("Kind, calm and on time.");
  await form.getByRole("button", { name: "Send review" }).click();
  await expect(page.getByRole("region", { name: "Your review" })).toBeVisible();
});
