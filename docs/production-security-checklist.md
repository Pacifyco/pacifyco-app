# Production security checklist

What to do when the phase 12 security work goes to production (the PR from `develop` to `main`). Tick
each box as you go. The background is in `docs/security-review.md`.

Never paste a key into chat, a file in the repo or a screenshot. Type keys only into your own terminal.

## Why the Data API is switched on only for the check

Supabase's **Data API** (its REST API) lets a browser read tables directly with the public key. Pacifyco
never uses it: the web app signs in with Supabase Auth and sends everything else through our own API.
So keep the Data API **off** in both projects. With it off, nobody can reach a table that way at all.

Row-level security (RLS) is the second layer: if the Data API were ever on, RLS would still refuse the
public key. The table check proves that layer works, and it can only run while the Data API is on. So for
each check: turn the Data API on, run the check, turn it off again.

The app never needs the Data API. It would only be needed if the web app started reading tables directly
from the browser, which CLAUDE.md rules out ("all writes and business logic go through the FastAPI API").

## Before the release PR (on staging)

- [ ] **1. Run the live Supabase check on staging.**
  1. **Turn the Data API on:** Supabase → `pacifyco-staging` → Project Settings → Data API → enable it,
     with `public` in "Exposed schemas". Give it a minute.
  2. **Run the check** from the API folder in your own PowerShell window (not with `!` in a Claude chat):

  ```
  cd C:\Users\josep\Reuben\pacifyco-app\api
  $env:SUPABASE_URL = "https://<staging ref>.supabase.co"
  $env:SUPABASE_SERVICE_ROLE_KEY = "<staging service-role key>"
  $env:SUPABASE_ANON_KEY = "<staging publishable key>"
  .venv\Scripts\python -m app.cli check-supabase
  ```

  Where to find the three values:
  - **URL:** Supabase → `pacifyco-staging` → Project Settings → API.
  - **Service-role key:** Render → `pacifyco-api-staging` → Environment → `SUPABASE_SERVICE_ROLE_KEY`.
  - **Publishable key:** Supabase → Project Settings → API Keys → publishable. It's the same as
    `VITE_SUPABASE_ANON_KEY` on Cloudflare.

  3. **Read the result.** Every line must say **PASS** (8 table lines, 5 storage lines). "not tested, the
     REST API didn't answer properly" means the Data API isn't on yet: wait a minute and run it again.
  4. **Turn the Data API off again:** Project Settings → Data API → disable it. Close the window.
- [x] **2. Check the web app's content policy on staging.** Done 2026-11-25: nothing reported.
  1. Open the staging site in Chrome and press F12 to open the Console.
  2. Use the app as a parent and as a sitter:
     - Sign in with an email code and with Google.
     - Open a sitter, book, and pay with a UPI reference.
     - Upload a file, open a booking, and check in.
  3. Look for any console message mentioning **Content-Security-Policy**.
- [x] **3. Turn the content policy on.** Done 2026-11-25 (enforced in `web/public/_headers`).
  - **If step 2 showed no messages:** in `web/public/_headers`, rename `Content-Security-Policy-Report-Only`
    to `Content-Security-Policy`. Merge that to `develop` and repeat step 2 on staging; the app should work
    the same.
  - **If step 2 showed messages:** fix the policy first. The messages name the blocked address. Don't ship
    an enforcing policy that blocks something.

## The release

- [ ] **4. Open and merge the PR from `develop` to `main`.** CI must be green; it now includes `pip-audit`
  and `npm audit`. The merge runs the production migrations and deploys both services.

## After the release (on production)

- [ ] **5. Run the live Supabase check on production.** Same as step 1, including turning the Data API on for
  the check and off afterwards, with production's values:
  - **URL:** Supabase → `pacifyco-prod` → Project Settings → API.
  - **Service-role key:** Render → `pacifyco-api` → Environment → `SUPABASE_SERVICE_ROLE_KEY`.
  - **Publishable key:** Supabase → `pacifyco-prod` → Project Settings → API Keys → publishable.

  Every line must say **PASS**. Note that the table check reads an empty table as "refused", so run it once
  production has at least one profile (your admin account counts).
- [ ] **6. Check the API's headers and that its docs are off.** In PowerShell:

  ```
  curl.exe -sI https://api.pacifyco.in/health
  curl.exe -s -o NUL -w "%{http_code}" https://api.pacifyco.in/docs
  curl.exe -s -o NUL -w "%{http_code}" https://api.pacifyco.in/openapi.json
  ```

  - **The first command's output** must include `x-content-type-options: nosniff`, `x-frame-options: DENY`,
    `cache-control: no-store` and `strict-transport-security: max-age=31536000; includeSubDomains`.
  - **The other two** must print `404`. If they print `200`, the Render service's `ENVIRONMENT` isn't set
    to `production`.
  - **Until DNS is set up,** use the Render URL instead of `api.pacifyco.in`.
- [ ] **7. Check the web app's headers.**

  ```
  curl.exe -sI https://www.pacifyco.in
  ```

  The output must include:
  - `x-content-type-options: nosniff` and `x-frame-options: DENY`.
  - `strict-transport-security`.
  - `permissions-policy` (with `geolocation=(self)`).
  - `content-security-policy` (not the `-report-only` one, after step 3).

  Until DNS is set up, use the Cloudflare Pages URL instead.
- [ ] **8. Use production once with the Console open (F12).** Sign in and open a few pages. There should be
  no Content-Security-Policy messages.
- [ ] **9. Check Supabase Auth's rate limits on production.** Supabase → `pacifyco-prod` → Authentication →
  Rate Limits. The limits on sending sign-in emails should be at or near the defaults, not raised. Do the
  same on `pacifyco-staging` if you haven't.
- [ ] **10. Confirm the API's rate limits are working.** Nothing to set up. Optionally, ask me to watch
  Sentry for `rate_limited` errors in the first week; a real person should never see one.

## Keep doing

- **When CI fails on "Dependency audit",** a new vulnerability was published in a package we use. Ask me to
  fix it (usually an upgrade), and don't release until it's green.
- **Run `check-supabase` again** on production after any change to Supabase settings, storage buckets or
  RLS, and every few months. Each time: Data API on, run the check, Data API off.
- **Keep the Data API off** in both projects. If you ever find it on and didn't turn it on, run the check
  at once, then turn it off.
- **If the API ever runs on more than one Render instance,** the rate limits need a shared store (Redis).
  Tell me before scaling.
