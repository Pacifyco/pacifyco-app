# progress.md — Pacifyco build progress

**How to use this file (Claude Code):** read it at the start of every session to find your place. Work
on the first unchecked item of the current phase. When an item is done and its tests pass, tick it
(`[x]`), update "Current status" and add one line to the session log. Items marked **[Reuben]** are for
Reuben; don't do them, but you may remind him when they block you. Don't tick anything with failing
tests.

## Current status

- Phase: 7 done (PR #96 merged 2026-11-20). Phase 8 ("During the booking") under way: check-in/check-out
  codes (PR #97, merged) and overdue check-out alerts + admin manual close (branch
  `phase8/overdue-checkout`) both built. Couldn't run the Postgres-backed API suite locally this session
  (no Docker here); web typecheck, lint and tests are green (348/349 — the 1 failure is the pre-existing
  Node 20 `Intl` midnight quirk, unrelated).
- Next item: phase 8, overtime request (parent picks whole hours, sitter accepts or declines).
- Beta uses a test UPI ID in `PACIFY_UPI_ID`; Reuben swaps in the company account before launch.
- Production sign-in: Resend key in prod SMTP and Cloudflare/Render Supabase variables; check after the next release to `main`
- `FIELD_ENCRYPTION_KEY` set on Render by Reuben (2026-11-03) — unblocks saving a sitter's health
  disclosure or bank details.

## Open questions (ask Reuben; don't guess)

- [x] **Sitter 15-minute late rule vs. the sitter-no-show report** (added 2026-11-20; answered by Reuben
  2026-11-20: "trash the 15 min late thing and add the 30 min no-show report mechanism"). The 15-minute
  table row is dropped; the 30-minute no-show report (built 2026-11-19) is what's kept, and is now the
  only mechanism. CLAUDE.md 6.5's table row and the "New cancellation rows" test row updated to match;
  the three legal documents that still described the 15-minute/cancel version (Sitter Terms of Use,
  Family Terms, sitter consent) updated in place to the 30-minute/report wording, with their fingerprints
  in `web/src/lib/legal.test.tsx` recomputed. The "paid only from check-in" half stays true in principle
  (6.2) but can't be built concretely until check-in exists (phase 8).
- [x] **Family Terms 4.3 and booking requests** (Reuben, 2026-11-19): 4.3 rewritten in place to match 6.4
  (the request goes to the sitter, who has up to 5 hours to accept; then the parent pays by 3 hours
  before the start). Fingerprint updated in `web/src/lib/legal.test.tsx`.
- [x] **A payment still unchecked when the booking starts** (Reuben, 2026-11-19): admins are emailed about
  it about an hour before the start (frequent job `alert_unchecked_payments`, once per payment), so it
  rarely happens. If it still does, the API refuses to confirm it (`booking_started`) and the admin
  contacts the parent; there's no way yet to record it as received and refund it.
- [x] **A paid booking whose child isn't verified by the start** (Reuben, 2026-11-18): until every child
  is verified the booking isn't confirmed or shown to the sitter, and doesn't block her time. If it loses
  the time to another confirmed booking, or the start comes first, it's cancelled and every payment is
  refunded. Built in "Unverified bookings don't hold the sitter's time" below.
- [x] Carry-forward cap: per child
- [x] Overtime shortfall: ₹300 per child per hour
- [x] Domain: pacifyco.in
- [x] Logo SVGs: Reuben adds them to the repo as files (see Phase 0)

- [x] **Sitter consent v1.0 vs the build rules** (added 2026-11-12; Reuben answered everything
  2026-11-12, now in CLAUDE.md 6.5, 6.8, 6.9, 6.11). Built word for word from Reuben's "Sitter consent"
  document (`web/src/content/sitter-consent-v1.0.md`, shown on `/sitter/consent`). Answers:
  1. Only a man at home: she declines and reports it with the new Issues button (no special button);
     parent pays the whole booking, no refund (Family Terms); no strike; flat ₹100 to the sitter.
  2. Overtime request: the parent picks whole hours, the sitter accepts or declines; charged at check-out.
     A parent who's late with no accepted request still pays overtime at check-out; UPI within 2 hours.
  3. Potty training and diaper changes: agreed in the in-app chat or in person at the 1-hour first
     booking. Pacify connects them in the app; after the first booking they may exchange numbers.
  4. Medicine instructions go in the child's medical notes (no new field; hint added on the family page).
  5. Wording stays; a theft report still suspends at once, and removal usually follows.
  Original questions:
  1. "If the only adult at home is a man ... decline the booking on the spot ... won't count as a strike,
     and you'll still receive ₹100": no such rule in 6.5 and no way to report it in the app. Is it a flat
     ₹100, or the show-up fee (₹100 per booked hour)? Does the parent pay for the booking?
  2. "If you need to stay longer, request overtime in the app": 6.8 says overtime is worked out
     automatically at check-out, with no request.
  3. "Potty training and diaper changes are something you and the parent agree on before the booking":
     nothing in the booking asks about it (chat opens only after a booking is confirmed, 6.11).
  4. "Medicine only if the parent has written the instructions in the app": medicine instructions aren't
     in the plan (see Family Terms point 10 below).
  5. "Theft means permanent removal": 6.9 says a theft report suspends her until an admin resolves it.

- [x] **Family Terms v1.0 vs the build rules** (added 2026-11-02; done 2026-11-13: Reuben asked to bring
  the terms in line with CLAUDE.md in place, no new version). Now in the terms: 18 months (1, 2, 4, 8),
  tick-only acceptance (3), overtime at check-out at the plan price (5), no rate on profiles (6), plans
  instead of packs (7, 8), no Aadhaar (13), no interviews. Kept from the terms: the full booking charged
  when a sitter leaves feeling unsafe (9), and the per-booking "who's at home", camera audio, introduction
  fee and marketing consent (10). For the lawyer at launch: "we store data in India" (12). The original
  list, for reference:
  points differ from CLAUDE.md or from what the app does. For each: change the rules (and app), or ask
  the lawyer for a new terms version?
  1. Minimum child age: terms say **2 years**; CLAUDE.md 6.4 and the Sitter Terms say **18 months**.
     **Decided: 18 months** (the app stays at 18 months). [Reuben] Family Terms need a new version (v1.1)
     saying 18 months, in 1.4, 3.8 and the cancellation table, before production families rely on it.
  2. Child below the minimum age at a booking: terms say the booked hours are **used up**; CLAUDE.md 6.5
     says the parent's hours are **refunded** (both say the sitter gets ₹100).
  3. Accepting the terms: terms say tick "I agree" **and confirm with an OTP sent to a verified mobile
     number**; the app has a tick only, phones aren't verified, and SMS is out of scope for v1.
  4. **Decided: follow the terms** (CLAUDE.md 7, "Consent"); built in phase 3.
     Consents: terms 11.2 say **four required and one optional consent, ticked separately at sign-up**;
     the app has one parental consent form, accepted later before child documents.
  5. Overtime when hours run out: terms say **₹300 per hour**; CLAUDE.md 6.8 says ₹300 **per child** per hour.
  6. Sitter rates: terms 3.1 say profiles show the sitter's **rate**; CLAUDE.md and design.md say parents
     never see it.
  7. Pricing: the table in 4.1 is the current pack pricing. **Replaced** by the plans below
     (answered 2026-11-03); Family Terms need a new version.
  8. Pack expiry: terms say 30 days after **purchase**; CLAUDE.md says after hours are **credited**
     (an admin confirms the UPI payment first).
  9. Sitter leaves because unsafe or the parent broke the terms: terms say the **full booking is charged**;
     CLAUDE.md 6.5 covers only the sitter's pay.
  10. **Decided for 2.5: follow the terms** (two emergency contacts per family, authorised adults;
      phase 3). Still not in the plan: medicine
      instructions (3.7), who else and which pets are home per booking (6.2), whether cameras record
      audio (6.3), the introduction fee to hire a sitter directly (7.2), an optional marketing consent
      (11.2), closing an account in the app and refunds when Pacifyco closes it (11.5).
  11. The terms' "24-hour safety line": the same number as the Sitter Terms' emergency line? (Built that
      way for now: both use `VITE_EMERGENCY_LINE`.)
  12. "We store data in India" (2.2, 11.1): accounts and documents are in Mumbai, but sign-in emails go
      through Resend (Tokyo) and error reports to Sentry (Germany, no personal data). Check the wording
      with the lawyer.
  13. **Added 2026-11-03.** Masked Aadhaar: terms 2.2 say Pacifyco collects the masked Aadhaar of both
      parents. Reuben decided the app will no longer collect it at all (dropped everywhere, see the
      session log) -- terms need a new version removing that line. Also leaves parent identity with no
      check at all beyond a birth certificate per child; confirm that's intended, or whether something
      should replace it.

- [x] **Pricing: plans instead of hour packs** (Reuben, answered 2026-11-03). Now in CLAUDE.md 6.1, 6.2,
  6.4, 6.5, 6.8 and 8: plans Pause ₹499 (one child), Unwind ₹699 (+₹150 per extra child), Recharge ₹899
  (any number); sitter levels set by admins, each working only her own plan, paid ₹200/300/400 an hour
  whatever the number of children; pay before the booking by UPI (admin confirms); refunds in money;
  overtime worked out at check-out, rounded up to the full hour, paid within 2 hours; parent not home =
  whole booking charged and ₹100 per booked hour to the sitter; no packs, no sitter rate, no minimum
  length, no GST. The sitter's own rate is removed (PR #58).
- [x] **Pricing follow-ups** (asked 2026-11-03, answered 2026-11-03). Now in CLAUDE.md 6.1, 6.4, 6.5, 6.8:
  1. No match deposit — dropped entirely. Parents pay the full price up front; encouraged (UX nudge, not
     enforced) to make a short first booking with a new sitter to assess fit.
  2. No slot hold while `pending_payment`: multiple parents can hold a pending booking for the same
     slot; first confirmed payment wins it, the others auto-cancel. Payment itself has a deadline: if
     not confirmed by 3 hours before the booking's start, it auto-cancels (new frequent job).
  3. Overtime past the plan's latest end is charged at the **next tier's** hourly rate (Pause→Unwind,
     Unwind→Recharge); sitter still paid her own level pay. **Still open:** Recharge has no higher tier
     — what's charged for overage past midnight on Recharge?
  4. Moot: bookings are whole hours only now (no half-hours), so the show-up fee is always a whole
     number of ₹100.
  5. Child under 18 months at a booking: parent charged for 1 hour, rest refunded; sitter paid for that
     hour, no strike.
  6. Level 3 reference-sharing consent: yes, a tick in the sitter's application.
  Also [Reuben]: **Sitter Terms v1.2** (2.3 rate, 2-hour minimum, per-child pay) and **Family Terms
  v1.1** (4.1 pricing, packs, overtime, 18 months) from the lawyer before production relies on them.
- [x] **Recharge overtime past midnight** (added 2026-11-03; deferred by Reuben 2026-11-03: "no idea,
  we'll see when we get there"). No higher tier exists above Recharge. Until decided, treat it like any
  other overtime past the latest end that has no next tier: round up to the full hour at the
  **Recharge** rate, sitter paid her level pay — revisit if/when it actually comes up.

- [x] **When does chat open?** (added 2026-11-08; answered 2026-11-08: "once there is a booking").
  Chat opens once the parent has a confirmed booking with the sitter (CLAUDE.md 6.11); no messaging
  before booking.
- [x] **Family Terms and introductions** (added 2026-11-08; done 2026-11-13): interviews removed; 3.2 now
  suggests a short first booking at home.
  Original note: the Family Terms may still describe a
  free introduction before the first booking; check and add to the v1.1 list for the lawyer.
  Reuben 2026-11-08: keep documenting the differences; the T&C will be changed later.

- [x] **Verification queue choices** (added 2026-11-08; answered 2026-11-08, CLAUDE.md 6.4 and 7):
  1. A family is verified only once **every** child's birth certificate is approved; adding a child
     sets it back to waiting. Parents can book before that, but a booking is confirmed only once its
     children are verified, and it doesn't show on the sitter's side until confirmed.
  2. A verified child's name and date of birth are locked (ask Pacify); parents can still add children.
  3. Rejected certificates are kept until a new one is uploaded.

- [x] **Psych test retake after a fail** (added 2026-11-03; answered 2026-11-08: "Admin should
  allow"). After a fail she can retake only once an admin presses "Allow a retake" on her review
  page (`POST /admin/psych-attempts/{id}/allow-retake`, audit `psych_retake_allowed`).

- [x] Parent late and declines overtime: answered 2026-11-03, overtime is worked out automatically at check-out and the sitter is paid for it (CLAUDE.md 6.8).

- [ ] **Parent consent document vs the build rules** (added 2026-11-13). Built word for word from Reuben's
  "Parent consent" document on `/parent/consent`; these points differ from CLAUDE.md. Change the rules
  (and app), or the document?
  1. "Be at home for the first **2** bookings with a new sitter": CLAUDE.md 6.3 suggests a **1-hour first
     booking** at home, as a nudge only.
  2. "If you're running late, your sitter can only stay on if they're available and you approve the
     overtime": CLAUDE.md 6.8 says the sitter can't leave the child, and overtime is worked out at
     check-out whether or not it was approved.
  3. "Outings and travel: let them know beforehand": CLAUDE.md 6.4 has outings on Recharge only, asked by
     the sitter and approved by the parent in the app during the booking; travel isn't in the plan.
  4. "Potty training and diaper changes ... agree on before the booking": chat opens only once a booking
     is confirmed (6.11), so that's in chat after booking, or in person.
  Also: are the screening questions (Screening_Questions.docx) from a licensed psychologist? Until
  confirmed, parents don't see a "Psychology screening passed" chip.

- [ ] **UX review (staging) items that need Reuben** (added 2026-11-13, from "Pacifyco web app — UXUI
  review (staging)"). Everything else in the review is built (see "UX review fixes" below). These
  clash with a rule in CLAUDE.md or design.md, need something only Reuben has, or are a new feature:
  1. **Booking as a request the sitter accepts within 30 minutes** (review #4, 07): CLAUDE.md 6.4 and
     design.md 12 say bookings confirm automatically once paid. Which wins? Booking is phase 7, so
     nothing is built either way yet.
  2. **Weekly availability confirmation with a Sunday WhatsApp check-in** (#5): a new rule, and
     WhatsApp is out of scope for v1 (CLAUDE.md 10).
  3. [x] **Notifications** (#6, 02.4, 05, 06.13, 07.1): answered 2026-11-13, approval emails now
     (Resend, `app/services/email.py`): a sitter when she goes live, a parent when a child is verified.
     WhatsApp stays out of v1. Rejection emails and an in-app bell weren't asked for.
     **[Reuben]** set `RESEND_API_KEY`, `EMAIL_FROM` and `PUBLIC_WEB_URL` on both Render services; until
     then nothing is sent (logged, never an error).
  4. [x] **Contact address** (01.3): answered 2026-11-13, founders@pacifyco.in everywhere, including the
     Family Terms, Sitter Terms and privacy policy (changed in place: no versions until the first
     release to main, Reuben 2026-11-13). Placeholders (TEST DATE, LLPIN) stay on the launch checklist.
  5. **Photos with emoji stickers over faces** (01.10): the review asks to *replace* them with photos
     whose faces are turned away, cropped or softly blurred; Reuben provides the photos. Swap the files
     in `web/src/assets/photos/` (design.md 8).
  6. **"Recharge" badge reads as jargon** (03.4): marked "Need to discuss". The badge is unchanged; the
     profile now explains the plan in plain words.
  7. **End of the sitter profile** (04.3): "Request a meet-and-greet" would claim a meeting before the
     first booking (dropped 2026-11-08, CLAUDE.md 7), and "Save to shortlist" is a new feature. Booking
     comes in phase 7; the 1-hour nudge stays until then.
  8. [x] **"Interviewed by the Pacify team"** (04.6): agreed 2026-11-13, "Joined Nov 2026" only.
  9. [x] **Child date of birth "age 2+" and "Infant"** (02.15, 06.1): agreed 2026-11-13, left out
     (Pacify books from 18 months).
  10. [x] **"If the only adult at home is a man" note in the Family Terms** (06.12): added in place
      2026-11-13 to 6.2 and the Section 5 table (sitter may decline, full booking charged). For the
      lawyer's launch review: lawful wording of a gender-based decline, and the fairness of charging the
      full booking.
  11. [x] **Area names for the pin codes** (02.14): done 2026-11-13 from the launch list, checked against
      OpenStreetMap (`web/src/lib/serviceArea.ts`): MG Road 560001, Koramangala 560034, Indiranagar
      560038, JP Nagar 560078, Lingarajapuram 560084, Koramangala 6th–8th Block 560095, Bellandur 560103.
      HSR Layout (560102) isn't a launch pin code. Reuben to correct any name.
  12. [x] **Reference quote** (04.1, 04.14): answered 2026-11-13, no.
  13. **More profile details** (04.9: skills, "Why I love working with kids") and **allergy against
      first aid** (04.10): new fields. Wanted?
  14. **Parent profile as a home base** (05) and the **sitter "today" screen** (07: tab bar,
      Accepting/Paused, pending requests, preview my profile): bigger redesigns that depend on 1 and 3.
      "Download or delete my data" is phase 10.
  15. **Find a sitter**: ages defaulting to the family's children and a "Filters · 1" bottom sheet
      (03 proposal) aren't built (there's no ages filter yet; one chip row instead of a sheet).
  16. **Parts of the day** (#9): picked Morning 9–1, Afternoon 1–6, Evening 6–10, Night 10–12, so they
      line up with the plans' latest ends (6 pm, 10:30 pm, midnight). OK?
  17. **"Fill ticked days" wiping slots** (#8, "Need to discuss"): now adds to the day and joins
      touching times (Mornings + Afternoons on Monday = 9 am–6 pm). OK?

---

## Phase 0 — Accounts and repo

- [x] [Reuben] GitHub repo created, `main` and `develop` branches, branch protection on `main`
- [x] [Reuben] Supabase projects `pacifyco-staging` and `pacifyco-prod` (Mumbai region)
  (Staging ref `yzunsmdzirfgybpmoipu`, prod ref `zbffwduowfdsypcxduex`, both ap-south-1, Data API off, automatic RLS on.)
- [x] [Reuben] Render account linked to GitHub
- [x] [Reuben] Cloudflare account linked to GitHub (delete the stray Workers project `pacifyco-app` it created; staging uses a Pages project)
- [x] [Reuben] Resend account; Sentry account with web and API projects
  (Sentry 2026-11-01: org `pacifyco` (EU region), projects `pacifyco-api` and `pacifyco-web`, error monitoring only, 100 events/hour per key, org-wide data scrubbing and no IP storage. Resend 2026-11-01: domain pacifyco.in verified (DNS at Hostinger), Supabase SMTP uses one Resend API key per environment.)
- [x] [Reuben] Google Cloud project (`Pacify`, 2026-11-01) with OAuth clients for sign-in, staging and
  production; app in Testing mode, publish before launch. Calendar API, service account and interview
  calendar **no longer needed** (interviews dropped 2026-11-08).
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
- [x] Scheduled jobs workflow skeleton calling `/internal/jobs/*` with `JOBS_SECRET`
  (`daily` and `frequent` runs verified by hand on staging and production. Frequent runs target production only until launch.)

## Phase 2 — Accounts, roles, service area, consent

- [x] Supabase sign-in (email OTP + Google) in web; API JWT verification and role loading
- [x] Role chooser and sign-up for parents and sitters; admin accounts created by seed/CLI only
- [x] Service area check on pin code at sign-up
- [x] Role-gated routes and API dependencies; suspended/removed users blocked
- [x] Parental consent form (versioned placeholder) and acceptance record
- [x] Sitter Terms of Use v1.1 page (move `content/sitter-terms-v1.1.md` to `/web/src/content/`; wording unchanged; placeholders from config); Privacy policy and Parent terms placeholder pages (versioned)
- [x] Click-wrap acceptance at sign-up for both roles; re-acceptance on new versions; acceptance records
- [x] Tests from CLAUDE.md section 9 for this phase

## Phase 3 — Verification and onboarding

`FIELD_ENCRYPTION_KEY` now set on Render (see Current status).

- [x] Parent consents at sign-up (Family Terms 11.2: four required, one optional) and the single-parent
  declaration, replacing the phase 2 consent form (single-parent declaration dropped 2026-11-03 with Aadhaar)
- [x] Emergency contacts per family (two) and authorised adults (Family Terms 2.5)
- [x] Private storage buckets, signed upload URLs, file type/size validation
- [x] Parent: children and emergency contacts, birth certificates (masked Aadhaar ×2 dropped 2026-11-03)
- [x] Sitter: application/profile (18+, health disclosure), government ID, college or work ID, police certificate, references, first-aid certificate, bank or UPI details, rate (₹80–120)
- [x] Psychology test engine with placeholder questions (backend PR #61, frontend PR #62)
- [x] Admin verification queue: view documents (logged), approve/reject each step with notes, set each sitter's level (CLAUDE.md 6.2)
- [x] Birth certificate auto-delete after child verification
- [x] Tests for this phase

## Phase 4 — New sign-up flow (added 2026-11-08, CLAUDE.md 6.13)

- [x] First sign-in asks only role (with confirmation) and terms, then goes straight to `/parent` or `/sitter`
- [x] Name, mobile, pin code (service-area check) and address move into the area as "finish your profile"
  (`PUT /me/details`, `/parent/details` and `/sitter/details`)
- [x] Parent area: checklist prompting to finish the profile (details, consents, children with birth
  certificates, emergency contacts); booking blocked until it's done (`GET /parent/checklist`;
  `checklists.require_finished_parent_profile` is the guard booking calls in phase 7)
- [x] Sitter area: checklist of onboarding steps with each step's status; not shown to parents until
  approved and live (`GET /sitter/checklist`; approval also needs her details, `details_missing`;
  search in phase 5 uses `verification.is_live`)
- [x] Booking stays unconfirmed until every child on it is verified (moved to phase 7, where booking is
  built; the rule and its test are listed there)
- [x] Tests for this phase
- Confirmed by Reuben 2026-11-08: a parent's profile is finished once everything is filled in and
  every birth certificate is uploaded (not yet verified); home address is required for both roles; the
  booking guard takes effect when booking is built in phase 7.

## Phase 5 — Marketplace

- [x] Sitter availability calendar (add/remove free times) — `/sitter/availability`
- [x] Geocoding with cache; distance from parent — Nominatim, 1 request/second, `geocode_cache`
- [x] Sitter search: distance, availability, rating, experience, languages, first aid —
  `GET /parent/sitters`, `/parent/sitters`; parents browse once their profile is finished (CLAUDE.md 7);
  strikes will also hide a blocked sitter once they exist (phase 9)
- [x] Sitter profile page and SitterCard (no price shown) — `/parent/sitters/:id`; the card's action is
  now "See [name]'s profile"
- [x] Recharge sitters' reference shown to parents with her consent (CLAUDE.md 6.2): a tick in the
  sitter application (`reference_shared_consent`), one admin-approved reference on her profile page
- [x] Tests for this phase

Interviews (the old phase 5) were dropped on 2026-11-08: no sitter onboarding interview, no
introductions, no Google Calendar. Parents are encouraged to make a 1-hour first booking with a parent
at home (CLAUDE.md 6.3).

## Onboarding polish (added 2026-11-09, before phase 6)

- [x] Sitter profile photo (JPG/PNG) in the application; parents see live sitters' photos
- [x] Rejection reason required from admins and shown to parents and sitters
- [x] Changes after a rejection go back for review (sitter steps 1-4; psych retakes stay admin-allowed)
- [x] Approval and rejection emails, brought forward 2026-11-13: sitter live or application rejected,
  child verified or certificate rejected, each sitter step, reference and psych test rejected (with the reason)
- [ ] [Reuben] Real psychology test questions (phase 15)
- [x] End-to-end tests (Playwright) for parent and sitter onboarding, admin review and finding a sitter;
  run in CI on every pull request (README "End-to-end tests")
- [x] Header: ☀️ / 🌙 theme switch (no "System") and a profile button whose bubble prompts people to
  finish their profile; the checklist moved from the home pages to "Your profile" (Reuben 2026-11-09)
- [x] Weekly availability: a week that repeats (quick fills: mornings, afternoons, evenings) plus days
  off; free times worked out for the next 14 days, the booking window (Reuben 2026-11-09)
- [x] Terms and privacy policy ticked on the consent pages, not at sign-up; new sitter consent page with
  Reuben's "Sitter consent" document (Reuben 2026-11-12)
- [x] Find a sitter lists every live sitter (no plan filter); filters are day, language, sort and first
  aid only, applied straight away; intro beside "Home" (Reuben 2026-11-09)

## UX review fixes (added 2026-11-13, from Reuben's staging review)

- [x] Consent first: step 1 on both checklists; children, emergency contacts and authorised adults
  refused before it (API + "Your consent comes first"); the sitter application waits for her consent
- [x] Referee phone numbers never shown to parents (API and copy)
- [x] Age groups and languages from fixed tap-chip lists (API validates; old free text hidden)
- [x] One parts-of-the-day model: availability quick fills (add, never wipe), "When?" filter, week grid
- [x] Errors name the field: sign-in email (checked on press, announced), consent boxes (outlined,
  focus moves), references, family and application forms
- [x] Checklists: one row per real step with the exact next action, status pill under the name, links
  to the exact step (`?step=`), "1 child · certificate needed"
- [x] Long text wraps on the sitter profile; dev link removed (`/dev/*` local and staging only)
- [x] Public pages: Google mark and "or" rules, no "Sign in" link on sign-in, phone headline, home CTA
  in the first screen, photos fade in once loaded, legal pages with an H1 and contents, 404 links
- [x] Parent: Required/Optional labels and an Optional divider, verified child "Verified 13 Nov" with
  no upload, Continue waits for a child, filters hidden until the profile is finished ("2 of 4 done"),
  bubble only on the home page, "Details saved" toast, +91 field and "+91 98450 12345", relationship
  dropdown, emergency contacts required, different from each other and from the parent's own number,
  pin codes listed, day/month/year date of birth, flatter child cards with actions in the footer,
  Sign out and theme in "Settings" on phones, progress bars
- [x] Find a sitter: "When?" chips (days and parts of the day), one chip row (First aid, languages),
  live count, sort beside it, filters in the address, empty results with "Remove First aid · 4 sitters",
  "Clear all filters" and "Ask the Pacify team"; shorter cards ("4 yrs · <1 km · Ages 1½–5")
- [x] Sitter profile: "Comfortable with ages 3–5", plan in plain words, "Joined Nov 2026", expandable
  trust badges, week grid with "Not available", languages, "Suits Diya (4)", photo left on desktop
- [x] Sitter: required "About you" with prompts, photo rules, file name and thumbnail after upload,
  "Add this reference", sitter wording on the details page, compact role cards with a tick, toasts
- [x] Sitter home: "Hi Asha.", application progress while not live, one-time "You're approved" card,
  "Get your first booking"
- [ ] The items in "Open questions" above, once Reuben decides

## Phase 6 — Plans and payments (was hour packs and ledger; changed 2026-11-03)

- [x] Pricing service (plans, children, whole hours only): `app/services/pricing.py`
- [x] Rates on sitter cards and profiles, never plan names (Reuben, 2026-11-17; replaces the plan picker:
  the sitter's level sets the plan, so parents pick a sitter, not a plan)
- [x] Book this sitter (simple form, from Phase 7 item 1, needed to pay): her free times, children, bath
  time, cameras, live price; starts at least 4 hours from now (`/parent/sitters/:id/book`,
  `app/services/bookings.py`; tables `bookings`, `booking_children`, `booking_home_info`). Checks whole
  hours, 4 hours' notice, her free times minus confirmed bookings, the plan's latest end, Pause one child,
  bath time, cameras, children 18 months+ and the parent's own. Money owed and strikes are checked once
  those exist
- [x] Booking payment: UPI instructions, UPI reference entry, `pending_payment` (no match deposit). The
  booking page shows Pacifyco's UPI ID (copy button), a "Pay in a UPI app" `upi://pay` link (payee
  Pacifyco, the amount and a "Pacifyco booking XXXXXXXX" note) and its QR code (`qrcode`), then takes the
  12-digit UPI reference (`POST /parent/bookings/{id}/payment`, `app/services/payments.py`): a `pending`
  `payments` row (migration f9ef16dd91b3) for an admin to check. Refused after the 3-hour deadline, twice
  for one booking (unless the last one was rejected) and for a reference already sent. The API's role can
  only add payment rows and update an admin's decision on them (status, confirmed_by, confirmed_at,
  rejection_reason). Without `PACIFY_UPI_ID` the page says payments aren't open yet
- [x] Frequent job: auto-cancel `pending_payment` bookings 3 hours before start; first confirmed payment
  wins a slot and auto-cancels the others. `cancel_unpaid_bookings` in the frequent run
  (`bookings.cancel_unpaid`): no payment sent by the deadline → `cancelled_unpaid`; a reference sent in
  time keeps the booking for an admin (Reuben, 2026-11-18). Also checked when the parent opens the
  booking, since the run skips midnight–6 am IST. `bookings.cancel_overlapping_unpaid` →
  `cancelled_slot_taken`, written and tested now; the admin's payment confirmation (next item) calls it.
  Statuses added in migration a1c3e5f7b9d2 (its downgrade refuses while such bookings exist)
- [x] Admin confirms/rejects payments; refunds recorded with a reference. `/admin/payments`
  (`PaymentsPage`): payments to check (with the plan, the UPI reference and note, and whether every child
  is verified), Confirm received or Reject with a reason the parent sees; refunds to pay, marked refunded
  with the transfer reference. Confirming makes the booking `confirmed`, or `awaiting_verification` if a
  child isn't verified (paid holds the slot, Reuben 2026-11-18; confirmed when the last child is approved,
  `bookings.confirm_verified`), and cancels overlapping unpaid bookings (their parents are emailed). Money
  for a booking that lost its slot is recorded and a refund is owed. Rejected after the deadline cancels
  the booking at once. Emails: paid, rejected, slot taken, refunded. Migration b2d4f6a8c0e1
- [x] Unverified bookings don't hold the sitter's time (Reuben, 2026-11-18). `awaiting_verification`
  left `HOLDS_TIME`; confirming a booking (`bookings.cancel_overlapping`) also cancels overlapping
  `awaiting_verification` bookings and refunds them; approving the last child confirms the booking or,
  if the time was taken, cancels and refunds it (`bookings.confirm_verified`); `cancelled_unverified` at
  the start, refunded (`bookings.cancel_unverified`, frequent job and on opening). Migration c3e5a7b9d1f4.
  Not emailed yet when the job cancels (jobs have no mailer); the parent sees it on the booking page
- [x] Parent payment history; outstanding amounts block new bookings. `/parent/payments` ("Your
  payments", from the parent's profile): every payment, charge and refund, newest first, linked to its
  booking, in plain words ("Pacifyco is checking it", "Paid", "Pacifyco is refunding you"). Money owed
  (`bookings.amount_owed`) = unpaid overtime and cancellation charges, which phases 7–8 create; booking
  payments being checked and refunds aren't owed. Owing anything refuses a new booking (409
  `money_owed`) and the booking page says so, with a link to Your payments. How a parent pays a charge
  comes with overtime (phase 8)
- [x] Remove the unused HourBalance component (and `formatHours`, which counted half-hour units)
- [x] Tests for this phase (checked against CLAUDE.md 9, 2026-11-18). Covered: price per plan and
  children, whole hours, `pending_payment` until an admin confirms, unpaid-by-deadline and rejected
  payments freeing the booking, append-only payment rows (grants), money owed = sum of unpaid charges,
  owing blocks booking, plan's latest end, bath time, two pending bookings for one slot with the first
  confirmed winning, unconfirmed until every child is verified, child age and camera declaration, audit
  rows, IDOR on every booking and payment endpoint. **Gaps found and fixed:** booking now refuses parents
  outside the service area (CLAUDE.md 1; it was only checked when the pin code was entered) and asks for a
  new terms version first (`terms_required`, not "finish your profile"); the booking page says why and
  links to where to fix it. **Left for their phases:** blocked-by-strike (7), refunds and cancellation
  charges per 6.5 (7), rate limiting on booking endpoints (12)

## Phase 7 — Bookings, cancellations, strikes

- [x] Book a time: plan and level match, plan's latest end, Pause one child, bath time, children 18 months+, camera declaration, parent profile finished, `pending_payment` → confirmed only once paid **and** every child is verified, remove availability; "try a 1-hour first booking at home" nudge with a new sitter
  Checked 2026-11-20: built in phase 6 (booking page and API), with requests (the sitter accepts first)
  and strikes (a blocked sitter can't be booked) since; each part has tests in test_bookings.py,
  test_requests.py, test_admin_payments.py and test_strikes.py
- [x] Parent and sitter booking lists and detail pages (sitters see only confirmed bookings)
  - Parent's side done 2026-11-18: a "Bookings" tab beside "Find a sitter" in the header (`AreaNav`),
    `/parent/bookings` (`GET /parent/bookings`) with Upcoming (soonest first) and Past (ended or cancelled,
    most recent first) tabs, each row opening the booking page (whose Back link now returns to the list).
    Opening the list cancels the parent's overdue unpaid or unverified bookings, as opening one does.
  - Sitter's side done 2026-11-19: "Home", "Bookings" and "Availability" tabs; `/sitter/bookings`
    (`GET /sitter/bookings`) with Upcoming and Past tabs, only bookings that were confirmed (never one
    waiting for payment or a child's verification). Each shows who, bath time, the family's camera
    answer and her pay for the booked hours (`services/sitter_pay.py`, 6.2), never the price or plan.
    Her home shows her next booking.
  - Sitter's booking page done 2026-11-19: `/sitter/bookings/:id` (`GET /sitter/bookings/{id}`, only her
    confirmed bookings, else 404): each child's age, allergies, medical notes (medicine) and routines,
    bath time, cameras, her pay. While it's ahead, the home address (Reuben, 2026-11-19: once
    confirmed) and the family's emergency contact; past or cancelled bookings leave them out. The
    parent's booking page was built in phase 6
- [x] Requests: the sitter accepts before the parent pays (Reuben, 2026-11-19; CLAUDE.md 6.4). The request
  shows to her once every child is verified; 5 hours to answer (or until 4 hours before the start);
  accepting holds her time and declines overlapping requests; lapsed or declined requests tell the
  parent; earliest start 6 hours ahead. Built 2026-11-19: statuses `requested`, `request_declined`,
  `request_lapsed` and `bookings.request_visible_at` (migration d4f6b8c0e2a5); sitter Requests tab
  (`/sitter/requests`) with Accept/Decline on the request page; emails to the sitter (new request) and
  parent (accepted, declined, lapsed); frequent job `lapse_requests`, also checked when opened.
  Family Terms 4.3 rewritten to match (Reuben, 2026-11-19)
- [x] Cancellations with 3-hour and 8-hour rules. `POST /parent/bookings/{id}/cancel` and
  `/sitter/bookings/{id}/cancel` (`services/cancellations.py`), with the consequence shown before they
  confirm. Refunds as `payments` rows; a late parent cancellation keeps the money (or owes it as a
  `cancellation_charge` if their payment is rejected); a late sitter cancellation records a strike
  (`strikes` table, migration 5683c7b4cb45; the ladder and blocking are the Strikes item). Emails to the
  other side, and to admins when a sitter cancels.
  - Paying a charge, built 2026-11-19 (brought forward from phase 8): `/parent/payments/:id` shows the UPI
    details and takes the reference (`POST /parent/payments/{id}/payment`); the "You owe" notice has a Pay
    now button; it joins the admin Payments queue, where confirming marks it paid and rejecting clears the
    reference with a reason. Still owed (blocking bookings) until confirmed. Overtime will use the same
    flow. Migration f7b9d1e3a5c6 lets the API's role set `payments.upi_reference`
- [x] Parent-absent (20-minute wait) and sitter no-show reports, admin confirmation, ₹100 per booked hour show-up fee.
  `booking_reports` (migration 1ae5f9ea87ab), `services/reports.py`. Sitter: "No one's home" (no child
  alone) and a 20-minute countdown; parent: "I have arrived" (Reuben, 2026-11-19), "Lakshmi didn't come"
  from 30 minutes after the start (Reuben, 2026-11-19); admin: `/admin/reports` (mark answered, confirm,
  dismiss with a reason). Confirmed no-show: refund and a strike. The show-up fee is recorded as the
  `parent_absent` status; paying it comes with payouts (phase 9). The Emergency button the sitter is told
  about isn't built yet (phase 8), so the copy points her to the parent, Pacifyco's number and 112
- [x] Sitter declines when the only adult at home is a man: reported with the Issues button, parent pays the whole booking, no strike, flat ₹100 to the sitter (decided 2026-11-12).
  Built 2026-11-20 as a third report kind (`only_man_home`, migration a8c0e2f4b6d7): "Only a man is at home"
  on her booking page once it's started; no wait; admin confirms on /admin/reports → `declined_man_at_home`.
  The Issues button (phase 8) can link to it; the ₹100 is paid with payouts (phase 9)
- [x] Under-18-months report (no strike) and unsafe early exit (no strike, full booking charged): built
  2026-11-20 as two more `booking_reports` kinds, `child_under_age` and `sitter_unsafe`, same pattern as
  "only a man at home". Child under 18 months: she reports it once an adult is with the child; confirmed,
  the parent is charged 1 hour and refunded the rest, she's paid her level pay for that hour. Unsafe exit:
  she reports it once the child is with a parent; confirmed, the whole booking stays charged (kept from
  the Family Terms), she's paid for the time she worked once check-in exists (phase 8/9). Also fixed a gap
  from the "only a man at home" PR: `declined_man_at_home` was never added to `SITTER_SEES`, so the sitter
  couldn't see that closed booking in her own list; added it there along with the two new statuses.
- [x] **Sitter 15-minute late rule**: dropped (Reuben, 2026-11-20); the 30-minute no-show report (above)
  is the only mechanism now. See "Open questions" for what changed in CLAUDE.md and the legal documents.
- [x] Strikes: ladder, blocking, 6-month expiry, admin add/remove. `services/strikes.py`; `sitters.blocked_until`
  (migration e495d3416292) hides a blocked sitter from parents, booking and accepting; the 5th strike
  removes her account (she and the admins are emailed). Expiry is by date, so no daily job (CLAUDE.md 5
  updated). Admin: Strikes on the sitter review page (give, remove with a reason, view a doctor's note).
  Sitter: `/sitter/strikes` and a notice on her home; a doctor's note for a late cancellation
  (`POST /sitter/strikes/{id}/doctor-note`). Bringing back a removed account is left to an admin
- [ ] Tests for this phase

## Phase 8 — During the booking

- [x] Check-in and check-out codes (parent's app, booking day only, single use, encrypted not hashed
  since the parent needs to see the same one again, lock after 5 wrong attempts) with location recorded.
  Built 2026-11-20: `api/app/services/checkin.py`; `GET /parent/bookings/{id}/check-in-code` (only once
  confirmed and on the day) and `/check-out-code` (only once checked in) generate a code the first time,
  then just return it again; `POST /sitter/bookings/{id}/check-in` and `/check-out` take the code and her
  location (`lat`/`lng`, left out if she denies permission), moving the booking to `in_progress` then
  `completed`. 5 wrong codes sets `codes_locked` and emails admins; nothing else can unlock it yet (see
  Current status). Migration c9e2a4f6b8d1
- [x] Overdue check-out alert job (end + 30 min) and admin manual close. Built 2026-11-20:
  `services/checkin.py` (`needing_attention`, `overdue_not_alerted`/`mark_overdue_alerted`,
  `close_by_admin`), frequent job `alert_overdue_checkouts`, `/admin/overdue-checkouts` (also lists
  codes-locked bookings, since they need the same remedy and had no way through until now — closes the
  gap flagged in the check-in/out PR) and `POST /admin/bookings/{id}/close` (reason required, audit
  logged). Admin home page shows a banner and a link when anything needs attention. Migration
  d3f5b7a9c1e4 adds `closed_by_admin` to the status list and `closed_by_admin_id`/`close_reason`.
  Backfilled the backend tests that PR #97 shipped without (`test_checkin.py`, new) alongside this
  item's own (`test_overdue_checkouts.py`).
- [ ] Overtime request: parent picks whole hours, sitter accepts or declines; charged at check-out (decided 2026-11-12)
- [ ] Issues button for parents and sitters (non-emergency: running late, only a man at home), a complaint linked to the booking (decided 2026-11-12)
- [ ] Overtime at check-out: rounded up to the full hour at the plan price, UPI link/QR due in 2 hours, unpaid blocks new bookings
- [ ] Emergency/Report button for parents and sitters; admin email alert; incident records
- [ ] Chat between a parent and sitter with a confirmed booking (polling)
- [ ] Outing permission requests during a booking (Recharge only)
- [ ] Tests for this phase

## Phase 9 — After the booking

- [ ] Reviews and ratings both ways; low-rating flag (last 10 < 3.5) with right to respond
- [ ] Sitter pay: level pay × hours worked, plus overtime; held → released rules
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

- [ ] Seed realistic data; extend the Playwright tests (onboarding journeys done 2026-11-09) to booking, check-in and payout journeys
- [ ] [Reuben] Manual functional test pass on staging
- [ ] [Reuben] User testing with ~5 parents and ~5 sitters; feedback logged in `docs/beta-feedback.md`
- [ ] Fix beta feedback items marked must-fix

## Phase 15 — Production launch

- [ ] [Reuben] Compliance done: DPDP consent text, pre-paid hours, GST, sitter tax status, privacy policy, parent terms (lawyer and CA) -- Aadhaar handling no longer applies, dropped 2026-11-03
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
- 2026-11-20 — Overdue check-out alerts (frequent job, once per booking) and admin manual close
  (`/admin/overdue-checkouts`, also listing codes-locked bookings; `POST /admin/bookings/{id}/close`),
  with a banner on the admin home page. Found and fixed a bug while writing tests: closing a booking
  that was never checked in would have tried to set `checked_out_at` without `checked_in_at`, violating
  the check constraint — fixed to leave it empty in that case. Also wrote `test_checkin.py`, the backend
  tests PR #97 shipped without. Branch `phase8/overdue-checkout`.
- 2026-11-20 — Phase 8 started: check-in and check-out codes, with location recorded and lockout after 5
  wrong attempts. Codes are encrypted (not hashed) since the parent needs to see the same one again.
  Branch `phase8/check-in-check-out`.
- 2026-11-20 — Reuben: drop the 15-minute late rule, keep only the 30-minute no-show report. CLAUDE.md's
  6.5 table and the "New cancellation rows" test row updated; the Sitter Terms, Family Terms and sitter
  consent wording updated in place to match (fingerprints recomputed in `legal.test.tsx`). Phase 7 is now
  fully decided; only CI confirmation of the Postgres-backed suite remains.
- 2026-11-20 — Under-18-months and unsafe-exit reports (two more `booking_reports` kinds, same pattern as
  "only a man at home"); fixed `SITTER_SEES` missing `declined_man_at_home`. Flagged the 15-minute late
  rule as an open question (looks superseded by the 30-minute no-show report) rather than guessing at it.
  Couldn't run the Postgres-backed API suite locally (no Docker here); web typecheck, lint and tests green
  (332/333, the one failure is the pre-existing Node 20 `Intl` midnight quirk), API lint and format green.
- 2026-11-20 — Ticked Book a time (checked against its tests); sitter declines when only a man is home.
- 2026-11-19 — Reports: parent not home (20-minute wait, I have arrived) and sitter no-show (from 30 minutes).
- 2026-11-19 — Paying a charge by UPI (late cancellation charges; overtime later).
- 2026-11-19 — Strikes: ladder, blocking, admin add/remove, doctor's note.
- 2026-11-19 — Cancellations (3-hour and 8-hour rules), strikes recorded for late sitter cancellations;
  parent list texts for requests. e2e 13.
- 2026-11-19 — Booking requests: the sitter accepts before the parent pays; earliest start 6 hours. e2e 12.
- 2026-11-19 — Sitter booking page: address once confirmed, children's care notes, emergency contact.
- 2026-11-19 — Sitter bookings list and home card; admins emailed about payments unchecked about an
  hour before the start. e2e 10.
- 2026-11-18 — Parent "Bookings" tab: upcoming and past bookings. e2e 9.
- 2026-11-18 — Unverified bookings no longer hold the sitter's time; cancelled and refunded if the time
  is taken first or the start comes (`cancelled_unverified`).
- 2026-11-18 — Phase 6 test check: booking now checks the service area and asks for new terms first;
  money-owed sum test. API 536, web 272, e2e 8. Phase 6 done.
- 2026-11-18 — Removed HourBalance and the half-hour `formatHours`. Web 269.
- 2026-11-18 — Parent payment history (`/parent/payments`) and money owed blocking new bookings.
  API 533, web 271, e2e 8.
- 2026-11-18 — Admin payments: confirm, reject, refunds with a reference, `awaiting_verification` (paid
  holds the slot), the admin Payments page and parent emails. API 525, web 266, e2e 7.
- 2026-11-18 — "Frequent job": unpaid bookings cancelled at the 3-hour deadline (job and on opening),
  overlapping unpaid bookings cancelled when one is confirmed; cancelled states on the booking page.
  API 512, web 257, e2e 6.
- 2026-11-18 — "Booking payment": `payments` table (append-only, decision columns only), UPI ID, link and
  QR code on the booking page, 12-digit UPI reference sent for an admin to check. API 501, web 255, e2e 6.
- 2026-11-18 — "Book this sitter": bookings tables (migration f6c8e0a2b4d5), booking options and create
  endpoints, the booking page with a live price, and a booking page that waits for payment (UPI details
  come next). API 484, web 250, e2e 6.
- 2026-11-17 — Phase 6 started (`plans-and-payments`). Reuben: parents see rates on sitter cards and
  profiles, never plan names; bookings start 4+ hours ahead; QR code approved (`qrcode`); test UPI ID for
  staging given. Pricing service and rates done. API 459, web 241 (one timing flake locally).
- 2026-11-16 — Reuben: sitters give their university and semester (1–10) in "About you", required;
  admins see them on the review page and parents on her profile page (migration `d4a6c8e0f2b1`; sitters who
  saved before are asked for them on the checklist). References, still optional, show "Done" only once she
  presses Continue on that step (`references_confirmed_at`, migration `e5b7d9f1a3c4`; sitters already past it
  are marked). Branch `sitter-university`. API 442, web 238 passed.
- 2026-11-13 — Reuben: after the emergency contact, parents see only "Your profile is under review";
  a sitter's reference is optional, one only, never her own number or one she gave before (removed
  references kept: migration `c1f3a5b7d9e2`); "References checked" shows only with an approved one.
  API 434, web 238, e2e 5 passed.
- 2026-11-13 — Reuben's parent list (`parent-steps-and-screening`): Parent consent document on the consent
  page; no subheadings on parent pages; four parent steps with a "Step N of 4" bar; the birth
  certificate is the add-child form's last field; the checklist's children link opens that step; the
  psych test is his 15 screening statements rated 1-5 (migration `b8d2e4f6a1c3`). Terms placeholders
  were already gone (PR #82). API 432, web 239, e2e 5 passed.
- 2026-11-13 — Sitter onboarding (Reuben): eight steps in order, each locked until the ones before are done
  (consent, details, about you with her photo, ID verification, health disclosure, references, payment
  details, psych test), a "Step N of 8" bar on each; all fields required except the police certificate
  (needed before approval) and the health disclosure (saved, even empty: migration `f9a1c3e5b7d2`);
  approval needs payment details; only the "submitted" message after the psych test; no days off.
- 2026-11-13 — Reuben's list (`profile-and-terms-cleanup`): no subheadings on the home page or the join
  confirmation; a generic privacy policy (no draft marker or version shown; lawyer review still due);
  parents give their relationship to their child in Your details (migration `e7b3d9f1a2c4`); one
  emergency contact, no authorised adults; the terms drop the LLPIN, registered office and emergency
  line. API 429, web 235, e2e 5 passed. Sign-in email wording is set in Supabase (dashboard).
- 2026-11-13 — Rejection emails (Reuben): a parent when a birth certificate is rejected; a sitter when a
  step, a reference, the psych test or her application is rejected; each with the admin's reason.
- 2026-11-13 — Reuben's tidy-ups (with the pinned header): no subheading on the join page; the terms say
  "Last updated: 13 Nov 2026" with no version (the `VITE_*_TERMS_DATE` variables are gone), and no
  version line on the consent pages; "Pacifyco" instead of "Pacifyco LLP"; the reference-sharing tick
  under first aid is removed, so parents see no Recharge reference for now. Web 242 passed.
- 2026-11-13 — Pinned header (`sticky-header`): stays at the top, hides while scrolling down, comes back on
  scrolling up with the page's Back link (iPhone 17 in the Google app hid the logo and Back, Reuben).
  Web 244, e2e 5 passed. Needs checking on Reuben's iPhone on staging.
- 2026-11-13 — The brand is "Pacifyco" in all copy, emails and messages (was "Pacify"); migration
  `c4e8b2a6d1f3` updates the placeholder psych questions. Privacy policy has a Back button to the page
  before (home if opened directly). API 425, web 243, e2e 5 passed.
- 2026-11-13 — `python -m app.cli reset-staging-accounts [--yes]` (`reset-staging-accounts`): removes every
  parent and sitter on staging with their records, files and sign-in accounts; admins stay; refuses
  production (Reuben). README "Starting staging again". API 424 passed.
- 2026-11-13 — Availability and filters (`availability-and-filters`, with `signin-box-below-photos`): quick fills removed; ticking a day adds 9–1 and each "+"
  adds the next of 1–4, 4–7, 7–10, 10–12, then stops (Reuben). Find a sitter (Reuben): "Pick a day"
  dropdown first (Today, Tomorrow, the day after, another date from a calendar, shown in the dropdown),
  then "When?" (Morning to Night), a multi-select Languages dropdown (API takes several, any of them)
  and the First aid chip. API 420, web 241, e2e 5 passed.
- 2026-11-13 — Home page: the sign-in box opens below the photos (Reuben); "Sign in or join" stays
  above them. Web 240 passed.
- 2026-11-13 — UX review fixes (`ux-review-fixes`), from Reuben's staging review: consent first (API
  refuses family data before it), no referee phones, fixed age/language lists, one parts-of-the-day
  model (`part` search filter), field-level errors, real checklist steps, Find a sitter "When?" filters
  in the URL, sitter profile and home reworked; 17 review items listed in Open questions for Reuben.
  API 414 passed, web 240 passed, e2e 5 passed. Then Reuben's answers: approval emails (Resend),
  founders@pacifyco.in, area names beside pin codes (API 419, web 240, e2e 5). Family Terms brought in
  line with CLAUDE.md in place (no versions until the first release to main).
  Sign-in is now a box on the home page ("Sign in or join" opens it); `/sign-in` redirects to `/?signin`.
  The footer links only to the privacy policy (the terms are linked from the consent pages), and the
  staging "Environment · API" line is gone. Final: API 419, web 240, e2e 5.
- 2026-11-12 — Consent pages (`consent-pages`): sign-up asks only the role; parents tick the Family Terms
  and privacy policy on `/parent/consent` with the consents (one POST); sitters get `/sitter/consent`
  with the sitter consent (new `legal_documents` kind `sitter_consent` v1.0, migration `a3c71e5b9d24`,
  fingerprinted) and the Sitter Terms and privacy policy. The area-wide "accept our terms" screen is gone;
  a new version reopens the consent step instead. Admins can't approve a sitter until she's accepted.
  Five lines of the sitter consent differ from the rules (Open questions). 404 API, 221 web, 5 e2e tests.
- 2026-11-10 — Reuben's UI tweaks: "← Your profile" back link on every profile form (details, consent,
  family, sitter application; screening links back to the application); small Submit on the screening,
  then an "application submitted" confirmation instead of a silent redirect; parent and sitter home tiles removed.
  Then: parents land on Find a sitter (no separate home); sitters land on "Your bookings" (asks a sitter
  with no week set to set her availability; otherwise changed from "Your profile"); "← Back" beside
  Continue on every step of the application and My family; the screening is one question at a time with Back.
- 2026-11-09 — End-to-end tests (`e2e-tests`): Playwright runs the onboarding journeys against the real
  web app and API on a fresh database, with stand-ins for Supabase and OpenStreetMap; new CI job. Found and
  fixed: the home checklist showed stale steps for up to 30 seconds after finishing one.
- 2026-11-09 — Weekly availability (`weekly-availability`): `weekly_hours` and `days_off` replace
  `availability_slots` (migration `d5577de53ca1`); `PUT /sitter/availability/week`, days-off
  endpoints; search and the parent's sitter page use free times worked out for 14 days; sitter page
  is a 7-day editor that fits a phone. Card plan label added. 399 API, 213 web, 5 e2e tests.
- 2026-11-09 — Find a sitter (`find-sitters-simpler`): `GET /parent/sitters` plan is optional (all
  levels by default) and takes `day` (free time left that India day); the page keeps only day,
  language (options from sitters' own languages), sort and first-aid, applied on change, with compact
  fields. Experience, rating and time-window filters stay in the API but aren't shown.
- 2026-11-09 — Header (`header-theme-profile`): sun and moon theme switch; profile button with a "finish
  your profile" bubble; checklist moved to `/parent/profile` and `/sitter/profile`, and steps return
  there; home pages trimmed to fit a phone screen. design.md 2 and 7 record the exceptions.
- 2026-11-09 — Onboarding polish (`onboarding-polish`): sitter profile photo (JPG/PNG; parents see
  live sitters' photos via signed URLs); admins must give a rejection reason, shown to parents and
  sitters on their checklist, family page and references; changes after a rejection go back for
  review. Migration `0d2ed5a4f50b`.
- 2026-11-08 — Phase 5 finished (`phase5/recharge-reference`): Recharge sitters' reference shown to
  parents with her consent (tick in the application); psych retakes now need an admin's "Allow a
  retake" (Reuben's answer). Migration `77b18ccb70f8`.
- 2026-11-08 — Phase 5 marketplace (`phase5/marketplace`): `availability_slots` and `geocode_cache`
  (migration `0de52ef87290`); sitters add and remove free times; homes geocoded with Nominatim on
  saving details (cached, 1 request/second, tests use a fake); `GET /parent/sitters` (live sitters of
  the plan's level; availability, rating, experience, language and first-aid filters; nearest, rating
  or experience sort) and `GET /parent/sitters/{id}`; Find a sitter and profile pages; SitterCard now
  links to the profile. 371 API and 192 web tests pass.
- 2026-11-08 — Phase 4 done (`phase4/new-signup-flow`): sign-up asks only role and terms;
  `profiles.full_name` nullable (migration `4b8e1f0c2a7d`); `PUT /me/details` (name, mobile, pin code
  with service-area check, address); parent and sitter checklists (`app/services/checklists.py`,
  `GET /parent/checklist`, `GET /sitter/checklist`) on each home page; sitter approval needs her details.
  344 API and 181 web tests pass.
- 2026-11-08 — Reuben answered the verification and chat questions. A family is now verified only
  once every child is approved, and adding a child sets it back to waiting (audit `parent_verification_reset`).
  Bookings show to sitters only once confirmed, and chat opens with a confirmed booking. Rules updated in
  CLAUDE.md 6.4, 6.11 and 7; 329 API tests pass.
- 2026-11-08 — Phase 3 done (`phase3/admin-verification-queue`): `onboarding_steps` table (admin
  reviews of profile, ID documents, police certificate), `sitters.level`, child verifier fields
  (migration `55d0da5cd21c`). `/admin/verifications` queue, sitter review (each step, references,
  psych test pass/fail, level, approve only when all five steps pass and a level is set; health
  disclosure behind its own logged endpoint), family review (approve/reject each child; approval
  deletes the birth certificate at once and verifies the parent). `verification.is_live` for search
  in phase 5. Web: queue, sitter and family review pages, linked from the admin home; parent home
  tiles no longer promise introductions or hour packs. 327 API tests (local Postgres) and 177 web
  tests pass; lint, typecheck and build clean. Three choices listed under Open questions.
- 2026-11-08 — Reuben: no sitter onboarding interview and no parent-sitter introductions (no Google
  Meet or Calendar); parents are encouraged, not forced, to make a 1-hour first booking at home. New
  sign-up flow: role and terms only, then straight into the area with "finish your profile" prompts;
  parents can't book until finished, bookings confirm only once children are verified; sitters show
  to parents once finished and approved. CLAUDE.md 1, 3, 4, 6.3, 6.4, 6.11, 6.13, 7, 8, 9 updated;
  new phase 4, old phase 5 removed; Google Calendar settings removed; copy promising introductions
  or interviews fixed.
- 2026-11-03 — Aadhaar dropped everywhere (Reuben: "we will not be taking aadhaar details anymore"):
  removed the `aadhaar_masked` document type and the `single_parent_declaration` consent kind (it
  existed only to stand in for a second Aadhaar) from the models, a new migration narrows both CHECK
  constraints (deleting any existing rows of those kinds first, since staging only -- nothing in
  production yet); removed `/parent/single-parent-declaration` and the two `consent.py` functions
  behind it; removed the now-unused `DocumentUploadList` component and its test (nothing else needs
  multi-slot upload); updated CLAUDE.md 7 and 8. Parent verification is now just a birth certificate
  per child plus admin approval -- flagged as an open question (no replacement ID check) and as a new
  Family Terms 2.2 mismatch, both above. Family page restructuring (below) also removed its Aadhaar
  section as part of the same change.
- 2026-11-03 — My family page restructured into a wizard (Reuben's request, matching the sitter
  application page): "My family" and its intro centered; one step at a time (Your children,
  Emergency contacts, Authorised adults) with Back/Continue navigation instead of a two-column page
  of every section at once. Finishing the last step navigates to `/parent` (no further onboarding
  page to hand off to, unlike the sitter side's psychology screening).
  166/167 web tests, 290 API tests pass (pre-existing Node 20 quirk on the web side); lint/typecheck/
  build clean on both; API tests not run against Postgres in this sandbox (no Docker) -- same as the
  psych test engine, confirm via CI before merging.
- 2026-11-03 — Sitter application page restructured into a wizard (`sitter/application-wizard`,
  Reuben's request): "Your application" and its intro centered; one step shown at a time (About you,
  Documents, Health disclosure, References, Payout details) with Back/Continue navigation instead of
  a two-column page of every section at once. Finishing payout details now navigates straight to
  `/sitter/psych-test` (dropped the separate status card, since the wizard is the path there now);
  finishing the psych test now navigates to `/sitter` instead of showing an inline "submitted" message
  on that page (the message still shows if she revisits that URL directly while pending/passed/failed).
  166/167 web tests pass (pre-existing Node 20 quirk), lint/typecheck/build clean.
- 2026-11-03 — Psychology screening frontend (`phase3/psych-test-frontend`, resubmitted): `/sitter/psych-test`
  page (radio options for multiple-choice, textarea for short-answer, prefills saved in-progress
  answers, checks every question is answered before PUT-then-POST submit, submitted/passed/failed
  views with a "Try again" after a fail); a status card on the sitter application page links to it.
  Built as part of PR #61, but that PR got merged (backend only) before these commits reached its
  branch -- GitHub had already deleted the branch, so pushing recreated it as an orphan with no open
  PR. Rebuilt as a clean cherry-pick onto current `develop` instead of reopening the stale branch.
  166/167 web tests pass (the one failure is the pre-existing Node 20 `format.test.ts` quirk);
  lint/typecheck/build clean.
- 2026-11-03 — Recharge overtime past midnight: Reuben deferred ("no idea, we'll see when we get
  there"). Defaulted CLAUDE.md 6.8 to charging the Recharge rate itself for now; revisit if it comes up.
- 2026-11-03 — `FIELD_ENCRYPTION_KEY` set on Render by Reuben; no longer blocking health
  disclosure/bank detail encryption.
- 2026-11-03 — Pricing follow-ups answered: no match deposit, no slot hold while `pending_payment`
  (first confirmed payment wins, others auto-cancel), 3-hour unpaid-booking auto-cancel deadline,
  bookings are whole hours only (no half-hours, replacing half-hour rounding), overtime past a plan's
  latest end is charged at the next tier's rate, under-18-months booking charges the parent 1 hour and
  refunds the rest (sitter paid for that hour, no strike), Level 3 reference-sharing consent is a tick
  in the application. CLAUDE.md 6.1/6.4/6.5/6.8/8 updated; no code yet. One sub-question still open:
  what's charged for Recharge overtime past midnight (no higher tier exists).
- 2026-11-03 — Pricing changed from hour packs to plans (Pause, Unwind, Recharge) and sitter levels: CLAUDE.md 6, 8 and 9 rewritten, phases 6-9 updated, follow-ups listed under Open questions. Sitter rate removed (PR #58). Family and Sitter Terms need new versions.
- 2026-11-02 — Checked the `format.test.ts` failure noted below: not a bug. The repo pins Node 24
  (`.nvmrc`, used by CI); on Node 20, `Intl` formats midnight differently, so one time test fails
  there. On Node 24 all 160 web tests pass. Use Node 24 on every machine. Recorded what to take from
  the portal design prototype in design.md section 12. `FIELD_ENCRYPTION_KEY` still to be set on Render.
- 2026-11-02 — Sitter application frontend (PR #55, open): `/sitter/application`, same two-column
  layout as the family page. Profile (age groups and languages as comma-separated free text -- no
  fixed taxonomy exists anywhere for either), health disclosure and payout details (bank or UPI)
  each wait for their own GET before mounting an editable form, applying the family-page emergency
  contacts fix up front this time instead of re-discovering the same race. References (add up to
  two, remove). Four document upload slots (government ID, college/work ID, police certificate,
  first-aid certificate) against the existing generic documents API, no backend changes needed.
  Linked from the sitter home page. 159 web tests pass (plus the `format.test.ts` failure, which
  only happens on Node 20; see the next entry). Item 5 is now fully built (#54 and #55 merged).
- 2026-11-02 — Sitter application backend (PR #54, merged): profile (bio, date of birth with an 18+
  check, years of experience, age groups, languages, first aid, hourly rate re-checked at the API
  against the same ₹80-120 range as the DB constraint), health disclosure and bank payout details
  encrypted at rest (new `app/services/encryption.py`, Fernet, keyed by a new
  `FIELD_ENCRYPTION_KEY` setting -- still needs setting on Render, same reminder as the service-role
  key), UPI payout with VPA format validation, new `references` table capped at two per sitter. ID,
  college/work ID, police certificate and first-aid certificate uploads needed no new code (the
  generic documents API already covers any type with no child). `accounts.is_empty` now also checks
  references. Found and fixed one bug before merge: encryption's first version called
  `get_settings()` directly instead of through FastAPI's dependency injection, so it silently
  ignored the test settings every test client builds and used the real (unset) env var instead --
  fixed by threading the key through like `app/services/storage.py` does. 286 API tests pass.
- 2026-11-02 — Family page frontend (PR #53, merged, needed #52): `/parent/family` with children
  CRUD (nested birth certificate upload per child), a two-contact emergency contacts form,
  authorised adults, and masked Aadhaar uploads (up to 2) with the single-parent declaration --
  two-column layout from the shared design artifact, our own components and rules. New reusable
  `DocumentUpload`/`DocumentUploadList` against the signed-upload-URL documents API. Found and
  fixed a real race while testing it: the emergency contacts form used to seed its fields as soon
  as the GET first resolved, so typing before that load finished could be overwritten by the seed;
  fixed by not rendering the editable form until the server data is in hand. 152 web tests pass
  (plus the pre-existing unrelated Node/Intl `format.test.ts` failure). Item 4 is now done (#52 and
  #53 both merged).
- 2026-11-02 — Emergency contacts and authorised adults (PR #51, backend only): `emergency_contacts` moved from per-child to per-family (two contacts, enforced by always replacing both together — Postgres can't express "exactly two rows" as a simple CHECK); new `authorised_adults` table for any number of named adults. `PUT /parent/emergency-contacts`, `GET`/`POST`/`DELETE /parent/authorised-adults` (ownership checked, no IDOR). `accounts.is_empty` now also checks both tables. No web page yet — comes with the next item ("Parent: children and emergency contacts..."). 249 API tests pass.
- 2026-11-02 — Parent consents at sign-up (PR #50): `consents` recreated as one row per (parent, kind, version) instead of one row per (parent, version) -- Family Terms 11.2's four required consents (own_data, child_data, share_care_details, emergency_authorisation) ticked separately, nothing pre-ticked, plus optional withdrawable marketing and a new `single_parent_declaration` kind ready for the masked-Aadhaar screen later (not wired to any UI yet). `documents.request_upload` now calls `require_current_consent` for any document with a `child_id`, closing a gap from the storage PR. Web `ConsentPage` shows the four checkboxes plus marketing; `AreaPages` updated. 233 API and 142 web tests pass.
- 2026-11-02 — Private storage buckets, signed upload URLs, file type/size validation (PR #49): `documents` and append-only `document_access_log` tables; private `documents` Supabase Storage bucket with a 5 MB / PDF-JPG-PNG limit, created by the migration (guarded for local/CI Postgres, which has no `storage` schema); `POST /documents/upload-url`, `POST /documents/{id}/confirm` (checks the real file bytes, not the filename, deletes and marks `invalid` on failure; IDOR-checked), `GET /admin/documents/{id}/view-url` (admin-only, every view logged). `app/services/storage.py` wraps Supabase Storage's REST API with the service-role key, swappable in tests. Also: design polish on the parent/sitter/admin home pages, a split-hero layout for sign-in and join, a loading buffer instead of a page flash during auth redirects (PRs #44, #45, #46, #47, #48). 230 API and 141 web tests pass.
- 2026-11-01 — Phase 2 done. Terms pages (PR #31): Sitter Terms v1.1 unchanged (fingerprint test), placeholders from VITE_ config, hidden in production until filled; parent terms and privacy drafts. Click-wrap (PR #33): legal_documents and append-only legal_acceptances, required at sign-up and after new versions. Crashes keep CORS headers (PR #34). Section 9 tests for this phase checked; booking/buying guards tested, wired up in later phases. 203 API and 128 web tests pass.
- 2026-11-01 — Role gates (PR #26): `require_role` routers for /parent, /sitter, /admin, blocked accounts 403, route sweep tests; web `RequireRole` and on-hold page. Pages centred (PR #27). Parental consent (PR #28, #29): append-only `consents`, `/parent/consent`, guard for phase 3 child documents. Verified on staging. 184 API and 105 web tests pass.
- 2026-11-01 — Sign-up (PR #21, #22): `/join` role chooser, name, Indian mobile and home pin code (launch pin codes only, `GET /service-area`), confirmation step; `POST /me/profile` once only; `python -m app.cli create-admin`. Role rules in CLAUDE.md 6.13. Verified on staging. 147 API and 82 web tests pass.
- 2026-11-01 — Sign-in (PR #18, #19): email code and Google via Supabase (PKCE), API verifies tokens against the project JWKS (ES256/RS256 only) and loads the profile, `GET /me`. Both projects on ECC signing keys; Resend SMTP; Google clients. Verified on staging. 99 API and 71 web tests pass.
- 2026-11-01 — Phase 1 done. Release PR #16 merged; scheduled jobs verified on staging and production.
- 2026-11-01 — Scheduled jobs skeleton: `/internal/jobs/{daily,frequent}` behind `JOBS_SECRET`, GitHub schedule (daily 2 am IST; frequent every 30 min, production only until launch). 80 API tests pass.
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
