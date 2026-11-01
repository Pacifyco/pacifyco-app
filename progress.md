# progress.md — Pacifyco build progress

**How to use this file (Claude Code):** read it at the start of every session to find your place. Work
on the first unchecked item of the current phase. When an item is done and its tests pass, tick it
(`[x]`), update "Current status" and add one line to the session log. Items marked **[Reuben]** are for
Reuben; don't do them, but you may remind him when they block you. Don't tick anything with failing
tests.

## Current status

- Phase: 1 — Foundation (Phase 0 [Reuben] items still open; they block the staging deploy items)
- Next item: Scheduled jobs workflow skeleton calling `/internal/jobs/*` with `JOBS_SECRET`
- Blocked on: nothing

## Open questions (ask Reuben; don't guess)

- [x] Carry-forward cap: per child
- [x] Overtime shortfall: ₹300 per child per hour
- [x] Domain: pacifyco.in
- [x] Logo SVGs: Reuben adds them to the repo as files (see Phase 0)

- [ ] Parent late and declines overtime: the sitter can't leave the child (terms 4.1) and can't check out without the parent's code. Is she paid for the extra time, and should that time be billed to the parent as overtime automatically?

---

## Phase 0 — Accounts and repo

- [x] [Reuben] GitHub repo created, `main` and `develop` branches, branch protection on `main`
- [x] [Reuben] Supabase projects `pacifyco-staging` and `pacifyco-prod` (Mumbai region)
  (Staging ref `yzunsmdzirfgybpmoipu`, prod ref `zbffwduowfdsypcxduex`, both ap-south-1, Data API off, automatic RLS on.)
- [x] [Reuben] Render account linked to GitHub
- [x] [Reuben] Cloudflare account linked to GitHub (delete the stray Workers project `pacifyco-app` it created; staging uses a Pages project)
- [ ] [Reuben] Resend account; Sentry account with web and API projects
  (Sentry done 2026-11-01: org `pacifyco` (EU region), projects `pacifyco-api` and `pacifyco-web`, error monitoring only, 100 events/hour per key, org-wide data scrubbing and no IP storage. Resend not started.)
- [ ] [Reuben] Google Cloud project with Calendar API, service account, interview calendar
- [ ] [Reuben] Business bank account and UPI ID for beta payments
- [x] [Reuben] Logo files added: wordmark and reversed wordmark (PNG, `assets/primary-logo*.png`), symbol (SVG). Web copies in `/web/src/assets/brand/`. SVG wordmarks still wanted from the designer (design.md section 6).

## Phase 1 — Foundation

- [x] Monorepo scaffold (`/web`, `/api`), `.env.example`, README with local setup
- [x] Local dev: Docker Compose Postgres for API tests, one command to run web + API
- [x] API skeleton: health endpoint, settings from env, Sentry, CORS, error format
- [x] Alembic set up; first migration with core tables from CLAUDE.md section 8; RLS enabled on all tables
- [x] Web skeleton: Vite + React + TS + Router + TanStack Query + Tailwind with design tokens, light/dark
- [x] UI components from design.md section 10 (Button, inputs, Chip, VerifiedChip, Card, IconTile)
  (Also built, display-only until their phases wire data: SitterCard, BookingCard, HourBalance, RoleChooser, EmergencyButton, EmptyState. Preview at `/dev/components`, not in production.)
- [x] CI: lint, type-check, tests on PRs (`.github/workflows/ci.yml`: Ruff + pytest on Postgres 17; ESLint + tsc + Vitest + build. Both jobs are required checks on `main` and `develop`. The API has no type checker yet; none is named in CLAUDE.md.)
- [x] Staging deploy: Render staging service, Cloudflare Pages `develop`, migrations run on merge
  (Web `https://pacifyco-web-staging.pages.dev`, API `https://pacifyco.onrender.com`. CI migrates staging as `postgres` after checks pass; Render deploys after CI; the API signs in as `pacifyco_api` (`/health/db` shows `api_role: true`). Settings in README "Staging deploy". Cloudflare preview deployments should be off.)
- [x] Production pipeline wired (deploys on `main`), not yet released
  (Web `https://pacifyco-web.pages.dev`, API `https://pacifyco-api.onrender.com`. First release PR #13 merged; CI migrated prod; `/health/db` shows `api_role: true`. Not announced; free plans until launch.)
- [ ] Scheduled jobs workflow skeleton calling `/internal/jobs/*` with `JOBS_SECRET`

## Phase 2 — Accounts, roles, service area, consent

- [ ] Supabase sign-in (email OTP + Google) in web; API JWT verification and role loading
- [ ] Role chooser and sign-up for parents and sitters; admin accounts created by seed/CLI only
- [ ] Service area check on pin code at sign-up
- [ ] Role-gated routes and API dependencies; suspended/removed users blocked
- [ ] Parental consent form (versioned placeholder) and acceptance record
- [ ] Sitter Terms of Use v1.1 page (move `content/sitter-terms-v1.1.md` to `/web/src/content/`; wording unchanged; placeholders from config); Privacy policy and Parent terms placeholder pages (versioned)
- [ ] Click-wrap acceptance at sign-up for both roles; re-acceptance on new versions; acceptance records
- [ ] Tests from CLAUDE.md section 9 for this phase

## Phase 3 — Verification and onboarding

- [ ] Private storage buckets, signed upload URLs, file type/size validation
- [ ] Parent: children and emergency contacts, masked Aadhaar ×2, birth certificates
- [ ] Sitter: application/profile (18+, health disclosure), government ID, college or work ID, police certificate, references, first-aid certificate, bank or UPI details, rate (₹80–120)
- [ ] Psychology test engine with placeholder questions
- [ ] Admin verification queue: view documents (logged), approve/reject each step with notes
- [ ] Birth certificate auto-delete after child verification
- [ ] Tests for this phase

## Phase 4 — Marketplace

- [ ] Sitter availability calendar (add/remove free times)
- [ ] Geocoding with cache; distance from parent
- [ ] Sitter search: distance, availability, rating, experience, languages, first aid
- [ ] Sitter profile page and SitterCard (no price shown)
- [ ] Tests for this phase

## Phase 5 — Interviews

- [ ] Onboarding interview for sitters (admin schedules)
- [ ] Introduction request: parent picks a slot in sitter availability
- [ ] Google Calendar event with Meet link and invites
- [ ] Admin records outcome; pair unlock on pass or prior booking
- [ ] Tests for this phase

## Phase 6 — Hour packs and ledger

- [ ] Pricing service (tiers, per child)
- [ ] Buy a pack: price shown, UPI instructions, UPI reference entry, `pending_payment`
- [ ] Admin confirms/rejects payments; credit ledger entry
- [ ] Ledger and balance views for parents (per child, nearest expiry, carried-forward hours)
- [ ] Daily expiry and carry-forward job
- [ ] Tests for this phase

## Phase 7 — Bookings, cancellations, strikes

- [ ] Book a time: validation (children 18 months+), camera declaration, auto-confirm, hold hours, remove availability
- [ ] Parent and sitter booking lists and detail pages
- [ ] Cancellations with 3-hour and 8-hour rules
- [ ] Parent-absent (20-minute wait) and sitter no-show reports, admin confirmation, ₹100 show-up fee
- [ ] Sitter 15-minute late rule, under-18-months report (parent refunded, sitter ₹100, no strike), unsafe early exit, doctor's note strike removal
- [ ] Strikes: ladder, blocking, 6-month expiry job, admin add/remove
- [ ] Tests for this phase

## Phase 8 — During the booking

- [ ] Check-in and check-out codes (parent's app, booking day only, single use, hashed, lock after 5 wrong attempts) with location recorded
- [ ] Overdue check-out alert job (end + 30 min) and admin manual close
- [ ] Overtime request and approval; balance debit; ₹300/hr dues; dues block new bookings
- [ ] Emergency/Report button for parents and sitters; admin email alert; incident records
- [ ] Chat between unlocked pairs (polling)
- [ ] Outing permission requests during a booking
- [ ] Tests for this phase

## Phase 9 — After the booking

- [ ] Reviews and ratings both ways; low-rating flag (last 10 < 3.5) with right to respond
- [ ] Sitter pay: rate × hours worked × children; held → released rules
- [ ] Sitter earnings dashboard (pending, paid)
- [ ] Admin payouts-due list with 12-hour countdown, alerts at 3 hours left and overdue; mark paid with transfer reference (bank or UPI)
- [ ] Tests for this phase

## Phase 10 — Admin panel completion

- [ ] Dashboard: open incidents, pending verifications, pending payments, today's payouts
- [ ] User management: suspend, remove, reinstate, strikes
- [ ] Bookings overview and manual adjustments (audit logged)
- [ ] Audit log and document access log views
- [ ] Complaints and grievances: Help → Raise a complaint, SLA timers, Grievance Officer escalation, appeals by a different admin
- [ ] Sitter account closure; data access, correction and deletion requests
- [ ] Tests for this phase

## Phase 11 — Notifications (email)

- [ ] Templates following design.md (600px, one button, "Warmly, the Pacify team")
- [ ] Verification outcomes, interview invites, booking confirmed/cancelled, overtime requests, pack credited, payout sent, incident alerts
- [ ] Tests for this phase

## Phase 12 — Security hardening (Claude Code owns this)

- [ ] Every item in CLAUDE.md section 9 "Security testing", with tests
- [ ] Report written to `docs/security-review.md` with findings and fixes

## Phase 13 — Marketing site (optional before beta)

- [ ] Scrollytelling landing page per brand guide chapters 01–06, waitlist form, "Become a sitter"
- [ ] Reduced-motion version, skip link, 360px and 200% zoom checks

## Phase 14 — Beta on staging

- [ ] Seed realistic data; Playwright smoke tests for parent, sitter and admin journeys
- [ ] [Reuben] Manual functional test pass on staging
- [ ] [Reuben] User testing with ~5 parents and ~5 sitters; feedback logged in `docs/beta-feedback.md`
- [ ] Fix beta feedback items marked must-fix

## Phase 15 — Production launch

- [ ] [Reuben] Compliance done: DPDP consent text, Aadhaar handling, pre-paid hours, GST, sitter tax status, privacy policy, parent terms (lawyer and CA)
- [x] [Reuben] Sitter Terms of Use v1.0 reviewed by lawyer
- [ ] [Reuben] Lawyer to confirm the v1.1 edits (2.4 check-out code and pay cap, 2.6 12-hour payouts, 4.8 18 months)
- [ ] [Reuben] Psychology test questions from a licensed psychologist (until then, don't show the "Psychology screening passed" chip to parents)
- [x] [Reuben] Domain bought: pacifyco.in
- [ ] [Reuben] DNS set up (www, staging, api, api-staging); Resend domain verified
- [ ] [Reuben] Production upgraded: Supabase Pro, Render Starter
- [ ] Legal placeholder pages replaced with approved text
- [ ] [Reuben] Fill sitter terms placeholders: date, LLPIN, registered address, Grievance Officer, privacy policy link, emergency line
- [ ] Production environment variables set and checked (no staging values)
- [ ] Release PR `develop` → `main`; migrations run; smoke test production
- [ ] Backups confirmed, Sentry alerts on, uptime monitor on

## Phase 16 — After launch

- [ ] Weekly: dependency updates, error review in Sentry
- [ ] v2 backlog: Aadhaar e-sign for the sitter agreement, Razorpay collection and payouts, WhatsApp/SMS, recurring bookings, Pacify Plus, more care types

---

## Session log (one line per session, newest first)
- 2026-11-01 — Production wired: release PR #13 merged, prod migrated by CI, API on `pacifyco_api` (`/health/db`), web and API in production mode with CORS limited to the production web origin.
- 2026-11-01 — Staging deploy done: `/health/db` confirms the API uses `pacifyco_api` on staging.
- 2026-11-01 — Staging live: web `pacifyco-web-staging.pages.dev`, API `pacifyco.onrender.com` (staging mode, CORS limited to the web origin), first staging migration run by CI. Added `/health/db` to prove the API's database login.
- 2026-11-01 — Staging deploy code: `pacifyco_api` DB role, staging migration job (GitHub environment `staging`, develop only), web Sentry, no personal data in Sentry from either app. Sentry projects checked and tightened. 55 API and 57 web tests pass.
- 2026-11-01 — CI (GitHub Actions): Ruff + pytest on Postgres; ESLint + typecheck + Vitest + build. `main` and `develop` both require PRs and both checks. Supabase staging confirmed in Mumbai. Render, Cloudflare, Supabase and Sentry GitHub apps installed on the org.

- 2026-10-31 — UI components (design.md section 10) in `web/src/components/ui`: Button/ButtonLink, TextInput/Select/Textarea, Chip, VerifiedChip (fixed labels for real checks only), Card, IconTile, SitterCard (no price prop), BookingCard, HourBalance, RoleChooser, EmergencyButton (confirm step), EmptyState; `lib/format.ts` for IST dates/times, hours and names. Lucide added. 53 web tests pass. Header now uses the wordmark (reversed in dark mode).
- 2026-10-31 — Web skeleton: React Router 7 (v8 needs React 19; stack is React 18), TanStack Query with an `apiFetch` that reads the API error format, Tailwind 4 mapped to design.md tokens (default palette removed), Poppins/Caveat, light/dark following the OS with a manual toggle and no flash. Placeholder parent/sitter/admin pages, 404 and error pages; environment footer outside production. 23 web tests pass. GitHub now auto-deletes merged branches.
- 2026-10-31 — Alembic + first migration: profiles, parents, children, emergency_contacts, sitters, service_area_pincodes (launch pins seeded), audit_log. RLS on every table (incl. alembic_version), no policies, anon/authenticated revoked incl. default privileges. Local DATABASE_URL falls back to Docker; `npm run dev` migrates. 45 API tests pass.
- 2026-10-31 — API skeleton: `/health`, typed settings from root `.env` (CORS required outside local, no `*`), Sentry on only when `SENTRY_DSN` set (no PII), one error format (`app/errors.py`, documented in CLAUDE.md section 5). 20 API tests pass.
- 2026-10-28 — Repo pushed (`main`, `develop`); `main` protected (PR required, no force-push or delete). Local dev: Docker Compose Postgres 17 (`pacifyco` + `pacifyco_test`), pytest `db_engine` fixture, root `npm run dev` starts DB + API + web.
- 2026-10-24 — Monorepo scaffold: /api (FastAPI shell, pytest) and /web (Vite + React 18 + TS, Vitest), root .env.example and README. Python moved from 3.12 to 3.14 (CLAUDE.md updated). One root .env read by both apps.
- 2026-10-23 — Sitter Terms of Use v1.1 added (per-child pay, 12-hour payouts, check-out code, 18-month minimum age); build rules aligned; bank or UPI payouts; complaints, outings, cameras and new cancellation rows added.
- 2026-10-23 — Added click-wrap terms acceptance for parents and sitters (CLAUDE.md section 7); Aadhaar e-sign moved to v2.
- 2026-10-20 — Added check-out code, overdue check-out alerts and admin manual close (CLAUDE.md 6.7).
- 2026-10-20 — Open questions answered (carry-forward and overtime per child, domain pacifyco.in). No code yet.
- 2026-10-20 — Files created: CLAUDE.md, design.md, progress.md. No code yet.
