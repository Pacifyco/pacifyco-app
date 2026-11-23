# Security review

Phase 12, 2026-11-23. Every item in CLAUDE.md section 9 "Security testing", what was checked, what was
found and what was fixed. Run against `develop` at the end of phase 11, before the beta.

## Summary

- **No one can reach another person's data.** The IDOR sweep found no holes: all 43 endpoints swept refuse
  another parent's or sitter's ids, and the victim's data is unchanged afterwards.
- **Fixed in this phase:**
  - One known vulnerability in a Python package.
  - Nine moderate ones in the web app's dev tools.
  - No rate limits.
  - No security headers on the API or the web app.
  - The API's interactive docs and schema were public.
- **Fixed earlier (phase 10):** the role-gate tests had silently checked nothing since a FastAPI upgrade.
- **Three things for Reuben** (at the end): run the live Supabase check on staging, turn the web app's
  content policy on after a staging check, and look at Supabase Auth's own rate limits.

## Each item

| Item (CLAUDE.md 9) | Result | Tested in |
| --- | --- | --- |
| Authorisation on every endpoint (IDOR) | No holes. Every parent, sitter and personal endpoint that takes an id refuses another person's id with 403 or 404 and says nothing about them. Admins are refused there too. The sweep reads the real routes, so new endpoints are covered | `api/tests/test_idor.py` |
| Role gates | Wrong role gets 403 on every role-gated endpoint; suspended, removed and closed accounts are blocked. **Finding (phase 10, fixed):** since FastAPI 0.162 the sweep found no routes, so it passed without checking; it now reads every route | `api/tests/test_roles.py` |
| RLS denies direct table access with the anon key | Every table has RLS with no policies; the browser roles have no table privileges (local database). **Live check added:** `check-supabase` asks staging's REST API for rows with the public key | `api/tests/test_migrations.py`, `api/app/security_check.py` |
| Storage buckets not publicly readable | The API uses a private bucket through the service key only. **Live check added:** `check-supabase` confirms the bucket is private and a file can't be read without a signed URL or a key | `api/app/security_check.py`, `api/tests/test_security.py` |
| Signed URL expiry | View URLs last 120 seconds, and every view is logged. **Live check added:** `check-supabase` confirms a signed URL stops working once it expires | `api/tests/test_security.py`, `api/tests/test_documents.py` |
| Input validation and upload limits | Uploads: PDF, JPG or PNG judged by the file's contents, at most 5 MB (complaint files too). Every request body has field types and lengths; validation errors never echo what was sent | `api/tests/test_documents.py`, `api/tests/test_skeleton.py` |
| Rate limiting on auth and booking endpoints | **Finding: there was none. Fixed:** limits per signed-in user on sign-up (5 a minute), booking (20 an hour), paying (10 an hour), complaints (10 an hour), complaint messages (30 an hour) and uploads (30 an hour), with `slowapi`. A refused request gets 429 `rate_limited`. Sign-in itself is Supabase Auth's | `api/tests/test_security.py` |
| CORS limited to our web origins | Only the configured origins; `*` is refused at start-up | `api/tests/test_skeleton.py` |
| Secure headers | **Finding: there were none. Fixed.** The API sends nosniff, frame denial, no referrer, a no-content policy and no-store on every response, errors included, plus HSTS outside local. The web app (`web/public/_headers`, Cloudflare Pages) sends nosniff, frame denial, a referrer policy, a permissions policy (location for check-in only) and HSTS, with a content policy in report-only mode until it's checked on staging. **Also found:** the API's `/docs`, `/redoc` and `/openapi.json` were public; now they're local only | `api/tests/test_security.py`, `web/src/securityHeaders.test.ts` |
| No secrets in the repo or logs | The scan of every tracked file finds no keys, tokens, DSNs or passwords, and no `.env` file but the example. Every log line is fixed text. Sentry sends no personal data. Errors never echo internal details | `api/tests/test_security.py`, `api/tests/test_skeleton.py` |
| Dependency audit | **Findings, fixed:** `opentelemetry-api` 1.45.1 (CVE-2026-126360, comes with FastAPI) now requires 1.45.2 or later; `cryptography` 48.0.1 (PYSEC-2026-3552, -3553 and -3554, published during this phase and caught by the new CI audit) now requires 50.x; 9 moderate issues in the web app's ESLint tooling (one `minimatch` flaw) were fixed with `npm audit fix`, and production packages had none. Both audits now run in CI on every PR, so a newly published vulnerability fails the build | `.github/workflows/ci.yml` |
| Jobs endpoints reject requests without `JOBS_SECRET` | Missing, wrong, longer, unprefixed and empty secrets are all refused with 401, for every run | `api/tests/test_jobs.py` |

## For Reuben

The full step by step for releasing this to production is `docs/production-security-checklist.md`.

1. **Run the live Supabase check on staging** (and on production before launch), from `api/` in your own
   terminal. The keys are staging's: the service-role key and the publishable (anon) key.

   ```
   SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... SUPABASE_ANON_KEY=... python -m app.cli check-supabase
   ```

   Every line should say PASS. It uploads one tiny test file and deletes it.
2. **Turn the web app's content policy on.** After this is on staging, open the browser's developer console
   there and use the app: sign in (email and Google), book, pay, upload a file, check in. If the console
   reports nothing about "Content-Security-Policy", rename `Content-Security-Policy-Report-Only` to
   `Content-Security-Policy` in `web/public/_headers`. If something is reported, send me the message.
3. **Look at Supabase Auth's rate limits** (Authentication → Rate Limits, both projects). They limit how
   often sign-in codes can be sent. The defaults are reasonable; make sure they haven't been raised.

## What's left as a known risk

- **Rate-limit counts are kept in the API's memory.** They reset when Render restarts or redeploys the
  service. If the API ever runs on more than one instance, each counts separately, and the counts would
  need to move to a shared store such as Redis.
- **The publishable (anon) key is public by design.** It's in the web app. RLS is what protects the data,
  which is why the live check matters.
- **The privacy policy still needs the lawyer's review** before production (phase 15).
- **A new vulnerability can fail CI at any time.** That's intended: fix it (usually an upgrade) and the build
  passes again.
