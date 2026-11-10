import { execFileSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { expect, test, type Browser, type Locator, type Page } from "@playwright/test";
import { FAKE, apiEnv, python } from "./env";

// The onboarding journeys end to end (CLAUDE.md 6.13, 7, 9): a parent and a sitter sign up and finish their
// profiles, an admin rejects a step with a reason, the sitter fixes it, the admin approves the sitter and the
// family, and the parent finds the sitter. The steps share one database, so they run in order.

type Person = { id: string; email: string; page: Page };

const run = randomUUID().slice(0, 8);
const PDF = { name: "document.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n% e2e test file\n") };
// A real 1x1 PNG, so the browser can show it as the sitter's photo.
const PNG = {
  name: "photo.png",
  mimeType: "image/png",
  buffer: Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    "base64",
  ),
};

/** A signed-in browser for a new person. Supabase keeps its session in localStorage; we put a token there. */
async function signIn(browser: Browser, label: string): Promise<Person> {
  const id = randomUUID();
  const email = `${label}-${run}@example.com`;
  const response = await fetch(`${FAKE}/e2e/token?sub=${id}&email=${encodeURIComponent(email)}`);
  const { token } = (await response.json()) as { token: string };
  const expiresAt = Math.floor(Date.now() / 1000) + 24 * 60 * 60;
  const session = {
    access_token: token,
    token_type: "bearer",
    expires_in: 24 * 60 * 60,
    expires_at: expiresAt,
    refresh_token: "e2e-refresh",
    user: { id, aud: "authenticated", role: "authenticated", email, app_metadata: {}, user_metadata: {} },
  };
  const context = await browser.newContext();
  await context.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    ["sb-localhost-auth-token", JSON.stringify(session)],
  );
  return { id, email, page: await context.newPage() };
}

/** The section (a step card) that holds this label's form. */
function sectionOf(page: Page, label: string | RegExp): Locator {
  return page.getByLabel(label).locator("xpath=ancestor::section[1]");
}

async function upload(page: Page, label: string, file: typeof PDF) {
  await page.getByLabel(label, { exact: true }).setInputFiles(file);
  await expect(page.getByText(label, { exact: true }).locator("..").getByText("Uploaded")).toBeVisible();
}

async function join(page: Page, role: "parent" | "sitter") {
  await page.goto("/join");
  await page.getByRole("button", { name: new RegExp(`I'm a ${role}`) }).click();
  await page.getByRole("button", { name: /Continue/ }).click();
  await expect(page.getByRole("heading", { name: `You're joining as a ${role}.` })).toBeVisible();
  await page.getByRole("checkbox", { name: /I agree to the/ }).check();
  await page.getByRole("button", { name: /Yes, create my account/ }).click();
  await expect(page).toHaveURL(new RegExp(`/${role}$`));
  // A bubble from the profile button in the header leads to the checklist.
  await page.getByRole("link", { name: "Finish your profile" }).click();
  await expect(page).toHaveURL(new RegExp(`/${role}/profile$`));
  await expect(page.getByRole("heading", { name: "Finish your profile" })).toBeVisible();
}

async function fillDetails(page: Page, name: string) {
  await page.getByRole("link", { name: /Your details/ }).click();
  await page.getByLabel("Full name").fill(name);
  await page.getByLabel("Mobile number").fill("98765 43210");
  await page.getByLabel("Home pin code").fill("560034");
  await page.getByLabel("Home address").fill("12, 4th Cross, Koramangala");
  await page.getByRole("button", { name: /Save my details/ }).click();
  await expect(page.getByRole("link", { name: /Your details/ }).getByText("Done")).toBeVisible();
}

let parent: Person;
let sitter: Person;
let admin: Person;

test.describe.configure({ mode: "serial" });

test("a parent signs up and finishes their profile", async ({ browser }) => {
  parent = await signIn(browser, "parent");
  const page = parent.page;
  await join(page, "parent");
  await fillDetails(page, "Priya Rao");

  await page.getByRole("link", { name: /Parental consent/ }).click();
  for (const name of [/use of my own data/, /use of each child's data/, /sharing my child's care details/, /emergency authorisation/]) {
    await page.getByRole("checkbox", { name }).check();
  }
  await page.getByRole("button", { name: "I agree" }).click();
  await expect(page.getByRole("link", { name: /Parental consent/ }).getByText("Done")).toBeVisible();

  await page.getByRole("link", { name: /Your children/ }).click();
  await page.getByRole("button", { name: "Add a child" }).click();
  await page.getByLabel("Child's name").fill("Asha");
  await page.getByLabel("Date of birth").fill("2022-03-01");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("heading", { name: "Asha" })).toBeVisible();
  await upload(page, "Birth certificate", PDF);
  await page.getByRole("button", { name: "Continue" }).click();

  const contacts = sectionOf(page, "Name").first();
  await expect(contacts.getByRole("heading", { name: "Emergency contacts" })).toBeVisible();
  const [names, relationships, phones] = [contacts.getByLabel("Name"), contacts.getByLabel("Relationship"), contacts.getByLabel("Phone")];
  await names.nth(0).fill("Meera Rao");
  await relationships.nth(0).fill("Grandmother");
  await phones.nth(0).fill("9876500001");
  await names.nth(1).fill("Vikram Rao");
  await relationships.nth(1).fill("Father");
  await phones.nth(1).fill("9876500002");
  await contacts.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByText("Step 3 of 3 · Authorised adults")).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/parent\/profile$/);
  await expect(page.getByText(/Your profile is finished, so you can book/)).toBeVisible();
  // Nothing left to do, so the home (Find a sitter) has no bubble.
  await page.getByRole("link", { name: "Home", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Find a sitter" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Finish your profile" })).toHaveCount(0);
});

test("a sitter signs up, applies and sets her week", async ({ browser }) => {
  sitter = await signIn(browser, "sitter");
  const page = sitter.page;
  await join(page, "sitter");
  await fillDetails(page, "Lakshmi Nair");

  await page.getByRole("link", { name: /About you/ }).click();
  await page.getByLabel("Date of birth").fill("1996-04-02");
  await page.getByLabel("Years of experience").fill("4");
  await page.getByLabel(/About you/).fill("I love storytime and long walks.");
  await page.getByLabel("Languages you speak").fill("English, Kannada");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByText("Step 2 of 5 · Documents")).toBeVisible();
  await upload(page, "Profile photo", PNG);
  await upload(page, "Government ID", PDF);
  await upload(page, "College or work ID", PDF);
  await upload(page, "Police clearance certificate", PDF);
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByText("Step 3 of 5 · Health disclosure")).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByText("Step 4 of 5 · References")).toBeVisible();
  for (const [name, phone] of [["Asha Iyer", "9876511111"], ["Ravi Kumar", "9876522222"]]) {
    await page.getByLabel("Name").fill(name);
    await page.getByLabel("Relationship").fill("Former employer");
    await page.getByLabel("Phone").fill(phone);
    await page.getByRole("button", { name: "Add reference" }).click();
    await expect(page.getByText(name)).toBeVisible();
  }
  await page.getByRole("button", { name: "Continue", exact: true }).click();

  await expect(page.getByText("Step 5 of 5 · Payout details")).toBeVisible();
  await page.getByLabel("Payout method").selectOption("upi");
  await page.getByLabel("UPI ID").fill("lakshmi@okaxis");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/sitter\/psych-test$/);
  // One question at a time: answer it (first option, or a short answer), then Next; Submit on the last.
  const progress = page.getByText(/^Question \d+ of \d+$/);
  for (;;) {
    const [current, total] = ((await progress.textContent()) ?? "").match(/\d+/g)!.map(Number);
    const radio = page.locator('input[type="radio"]').first();
    if (await radio.count()) await radio.check();
    else await page.locator("textarea").fill("I stay calm and keep the child safe.");
    if (current === total) break;
    await page.getByRole("button", { name: "Next" }).click();
    await expect(progress).toHaveText(`Question ${current! + 1} of ${total}`);
  }
  await page.getByRole("button", { name: "Submit" }).click();
  // Submitting confirms the application is in; from there she goes to her profile checklist, where the
  // screening is now with Pacify.
  await expect(page.getByText("Your application is submitted.")).toBeVisible();
  await page.getByRole("link", { name: "Go to your profile" }).click();
  await expect(page).toHaveURL(/\/sitter\/profile$/);
  await expect(page.getByRole("link", { name: /Psychology screening/ }).getByText("Being checked")).toBeVisible();

  // Her usual week: Mornings on every weekday, in one tap, plus a day off.
  await page.goto("/sitter/availability");
  await page.getByRole("button", { name: "Mornings" }).click();
  await page.getByRole("button", { name: "Save my week" }).click();
  await expect(page.getByText("Saved. It repeats every week until you change it.")).toBeVisible();
  const inAWeek = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  await page.getByLabel("Day", { exact: true }).fill(inAWeek);
  await page.getByRole("button", { name: "Mark day off" }).click();
  await expect(page.getByRole("button", { name: /^Remove day off / })).toBeVisible();

  await page.goto("/sitter/profile");
  for (const step of ["About you", "ID documents", "Police clearance certificate", "References", "Psychology screening"]) {
    await expect(page.getByRole("link", { name: new RegExp(step) }).getByText("Being checked")).toBeVisible();
  }
});

test("an admin rejects a step with a reason; the sitter sees it and uploads again", async ({ browser }) => {
  admin = await signIn(browser, "admin");
  execFileSync(python, ["-m", "app.cli", "create-admin", "--email", admin.email, "--name", "Pacify Admin", "--user-id", admin.id], {
    cwd: "../api",
    env: { ...process.env, ...apiEnv },
  });
  const page = admin.page;
  await page.goto("/admin");
  await page.getByRole("link", { name: /Open the verification queue/ }).click();
  await page.getByRole("link", { name: /Lakshmi Nair/ }).click();

  const police = sectionOf(page, "Notes on the police certificate");
  await police.getByLabel("Reason for rejecting the police certificate").fill("It's older than six months.");
  await police.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(police.getByText("Rejected")).toBeVisible();

  const sitterPage = sitter.page;
  await sitterPage.goto("/sitter/profile");
  const item = sitterPage.getByRole("link", { name: /Police clearance certificate/ });
  await expect(item.getByText("Needs another look")).toBeVisible();
  await expect(item.getByText("Reason: It's older than six months.")).toBeVisible();

  await item.click();
  await sitterPage.getByRole("button", { name: "Continue" }).click();
  await upload(sitterPage, "Police clearance certificate", PDF);
  await sitterPage.goto("/sitter/profile");
  await expect(sitterPage.getByRole("link", { name: /Police clearance certificate/ }).getByText("Being checked")).toBeVisible();

  await page.reload();
  await expect(sectionOf(page, "Notes on the police certificate").getByText("Waiting")).toBeVisible();
});

test("the admin approves the sitter and the family", async () => {
  const page = admin.page;
  for (const subject of ["the profile", "the ID documents", "the police certificate", "Asha Iyer's reference", "Ravi Kumar's reference"]) {
    // Each decision form: the nearest box around this notes field that has buttons.
    const form = page.getByLabel(`Notes on ${subject}`).locator("xpath=ancestor::div[.//button][1]");
    await Promise.all([
      page.waitForResponse((response) => response.request().method() === "POST" && response.ok()),
      form.getByRole("button", { name: "Approve", exact: true }).click(),
    ]);
  }
  await page.getByRole("button", { name: "Pass" }).click();
  await page.getByLabel("Level").selectOption("pause");
  await page.getByRole("button", { name: "Save level" }).click();
  await page.getByRole("button", { name: "Approve and go live" }).click();
  await expect(page.getByText("Approved", { exact: true }).last()).toBeVisible();

  await sitter.page.goto("/sitter/profile");
  await expect(sitter.page.getByText("Your profile is live. Families can now find and book you.")).toBeVisible();

  await page.goto("/admin/verifications");
  await page.getByRole("link", { name: /Priya Rao/ }).click();
  await page.getByLabel("Notes on Asha's birth certificate").locator("xpath=ancestor::li[1]").getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByText(/The birth certificate has been deleted/)).toBeVisible();
});

test("the parent finds the sitter, with her photo and no prices", async () => {
  const page = parent.page;
  await page.goto("/parent/profile");
  await expect(page.getByRole("link", { name: /Your children/ }).getByText("Approved")).toBeVisible();
  // Home is Find a sitter.
  await page.getByRole("link", { name: "Home", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Find a sitter" })).toBeVisible();

  const card = page.getByRole("article").filter({ has: page.getByRole("heading", { name: "Lakshmi Nair" }) });
  await expect(card).toBeVisible();
  await expect(card.getByText("4 years' experience · under 1 km away")).toBeVisible();
  const photo = card.getByRole("img", { name: "Lakshmi Nair" });
  await expect(photo).toBeVisible();
  expect(await photo.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
  await expect(page.locator("body")).not.toContainText("₹");

  await card.getByRole("link", { name: "See Lakshmi's profile" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Lakshmi Nair" })).toBeVisible();
  await expect(page.getByText("I love storytime and long walks.")).toBeVisible();
  await expect(page.getByText("Mon", { exact: true })).toBeVisible();
  await expect(page.getByText("9 am – 1 pm").first()).toBeVisible();
  await expect(page.getByText(/^Not free on /)).toBeVisible();
  await expect(page.getByText(/Start with a 1-hour booking while you're at home/)).toBeVisible();
  await expect(page.locator("body")).not.toContainText("₹");
});
