import { randomUUID } from "node:crypto";
import type { Browser, BrowserContextOptions, Page } from "@playwright/test";
import { FAKE } from "./env";

// Signing in as a new person in the end-to-end tests, shared by the journeys.

export type Person = { id: string; email: string; page: Page };

const run = randomUUID().slice(0, 8);

/** A signed-in browser for a new person. Supabase keeps its session in localStorage; we put a token there. */
export async function signIn(browser: Browser, label: string, options: BrowserContextOptions = {}): Promise<Person> {
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
  const context = await browser.newContext(options);
  await context.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    ["sb-localhost-auth-token", JSON.stringify(session)],
  );
  return { id, email, page: await context.newPage() };
}
