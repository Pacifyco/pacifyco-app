# CLAUDE.md — Pacifyco build guide

Read this file and `progress.md` at the start of every session. Read `design.md` before any UI work.
Do not re-read the whole codebase to find your place: `progress.md` says where we are.

---

## 1. What Pacifyco is

Pacify (company: Pacifyco) is a babysitter marketplace for parents in Bengaluru. Parents browse vetted
sitter profiles, meet a sitter in a free Google Meet introduction run by the Pacify team, then book
scheduled care paid from pre-bought hour packs. Pacify vets everyone, can suspend or remove any user,
and pays sitters within 12 hours of each booking.

- Care type: babysitting only.
- Launch pin codes (sign-up and bookings blocked elsewhere): 560001, 560034, 560038, 560078, 560084,
  560095, 560103.
- Roles: `parent`, `sitter`, `admin`.
- Delivery: one mobile-first responsive web app (no native apps in v1).

---

## 2. Working rules for Claude Code

1. **One task at a time.** Pick the next unchecked item in `progress.md`, finish it with its tests,
   then tick it and add one line to the session log. Never start the next phase while the current one
   has failing tests.
2. **Don't over-engineer.** No new library, service, abstraction layer or microservice unless this file
   names it or the task can't be done without it. If you think one is needed, stop and ask.
3. **Business rules live in section 6.** Implement them exactly. If a rule is ambiguous or missing, do
   not invent one: add it to "Open questions" in `progress.md` and ask.
4. **Branches.** Work on feature branches off `develop`. `develop` deploys to staging, `main` deploys to
   production. Never push to `main` directly; production releases are a PR from `develop` to `main`
   that Reuben approves.
5. **Secrets.** Never commit secrets or paste them into code, logs, tests or chat. Read them from
   environment variables. Keep `.env.example` up to date with every variable name (no values).
6. **Tests are part of done.** Every feature ships with the tests listed for it in section 9. Reuben
   runs manual functional tests on staging; you own automated tests and security testing.
7. **Database changes only through Alembic migrations.** Never edit the database by hand. Every
   migration must run cleanly on an empty database and be reversible where practical.
8. **Copy follows `design.md` voice rules.** Never claim a safety check we don't do (see section 7).
9. **Keep context small.** Update `progress.md` instead of writing summaries in chat. Don't paste large
   files back into the conversation.
10. **When something breaks badly,** stop, report what happened and what you'd roll back. Don't keep
    stacking fixes.

---

## 3. Stack and services (free tiers during build and beta)

| Layer | Choice |
| --- | --- |
| Frontend | React 18 + TypeScript + Vite, React Router 7 (v8 needs React 19), TanStack Query, Tailwind CSS mapped to the tokens in `design.md`, Lucide icons (stroke 1.75) |
| Backend | Python 3.14 (same version locally, in CI and on Render), FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, psycopg 3 |
| Database, auth, file storage | Supabase (Postgres, Auth, private Storage buckets), Mumbai region |
| Frontend hosting | Cloudflare Pages |
| API hosting | Render (web service) |
| Email | Resend |
| Interview scheduling | Google Calendar API (creates Google Meet links and invites) |
| Maps and distance | OpenStreetMap: Nominatim for geocoding (cache results, max 1 request/second, set a User-Agent), Leaflet for maps |
| Error tracking | Sentry (frontend and API) |
| CI/CD | GitHub Actions; Cloudflare Pages and Render auto-deploy from branches |
| Lint (dev only) | ESLint with typescript-eslint and react-hooks (web), Ruff for lint and formatting (API) |
| Scheduled jobs | GitHub Actions `schedule` workflows calling protected API endpoints |
| Payments (beta) | None. Parents pay by UPI to the business account; admins verify and credit hours. Sitters are paid manually by bank transfer or UPI within 12 hours of check-out. |
| Payments (later) | Razorpay for collection and automated payouts. Design the payment code behind one small interface so it can be swapped in. |

At production launch Reuben upgrades production to Supabase Pro and Render Starter (no pausing, no cold
starts, daily backups). Staging stays on free tiers.

### Repository layout

```
/web            React app (parent, sitter and admin areas in one app, role-gated routes)
/api            FastAPI app
  /app
    /routers    one router per area: auth, profiles, documents, sitters, search, interviews,
                packs, ledger, bookings, overtime, checkins, incidents, chat, reviews,
                payouts, admin, jobs
    /services   business rules (pricing, ledger, cancellations, strikes, payouts)
    /models     SQLAlchemy models
    /schemas    Pydantic schemas
  /alembic      migrations
  /tests
/.github/workflows
CLAUDE.md  design.md  progress.md  .env.example
```

---

## 4. Environments

Staging and production are identical code with separate services, databases and keys.

| | Staging | Production |
| --- | --- | --- |
| Git branch | `develop` | `main` |
| Web | `https://staging.pacifyco.in` | `https://www.pacifyco.in` (`pacifyco.in` redirects to `www`) |
| API | `https://api-staging.pacifyco.in` | `https://api.pacifyco.in` |
| Render service | `pacifyco-api-staging` | `pacifyco-api` |
| Supabase project | `pacifyco-staging` | `pacifyco-prod` |
| Resend | test sender | verified domain sender |
| Google Calendar | test calendar | Pacify calendar |
| Sentry environment | `staging` | `production` |
| Seed data | yes (fake parents, sitters, bookings) | never |

The domain is `pacifyco.in`. Keep URLs in config (`PUBLIC_WEB_URL`, `VITE_API_URL`), never hard-coded.
Until DNS is set up, use the default Cloudflare Pages and Render URLs.

### Pipeline

- Pull request to `develop`: lint, type-check, run all tests.
- Merge to `develop`: run tests, run `alembic upgrade head` against staging, then Render and Cloudflare
  auto-deploy staging.
- PR `develop` → `main` (Reuben approves): same checks; on merge run migrations against production, then
  auto-deploy production.
- Staging Supabase may pause after a week idle; the daily jobs workflow keeps it in use.

### Environment variables (`.env.example`)

API: `ENVIRONMENT`, `DATABASE_URL`, `MIGRATION_DATABASE_URL` (CI only), `SUPABASE_URL`, `SUPABASE_JWKS_URL` (or `SUPABASE_JWT_SECRET`,
whichever the project uses), `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `EMAIL_FROM`,
`ADMIN_ALERT_EMAILS`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_CALENDAR_ID`, `SENTRY_DSN`,
`JOBS_SECRET`, `PUBLIC_WEB_URL`, `CORS_ORIGINS`, `PACIFY_UPI_ID`.

Web: `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_SENTRY_DSN`,
`VITE_ENVIRONMENT`.

---

## 5. Architecture decisions

- **All writes and business logic go through the FastAPI API.** The web app uses Supabase only for
  sign-in (email OTP and Google). The API verifies the Supabase JWT on every request and loads the
  user's role from the `profiles` table.
- **Row Level Security on every table** with no policies for the `anon` and `authenticated` roles, so
  the database can't be read directly from the browser even by mistake. The API connects with its own
  database role, `pacifyco_api` (BYPASSRLS; reads and writes rows, can't change tables; `audit_log` is
  insert-only). Migrations run as the database owner. New tables get the API's grants automatically;
  new append-only tables must revoke UPDATE and DELETE in their migration.
- **Sentry collects errors only** (no tracing, replay or logs) and no personal data: user info, cookies,
  headers, request bodies, query strings and local variables are all off in both SDKs.
- **Storage buckets are private.** Uploads go through signed upload URLs issued by the API. Files are
  viewed only by admins through short-lived signed URLs, and every view writes a row to
  `document_access_log`.
- **Money** is stored as integer paise. **Time** is stored in UTC (`timestamptz`) and shown in
  Asia/Kolkata.
- **Hours** are stored as integer half-hour units ("units"), so 2.5 hours = 5 units. Hour balances are
  child-hours (see section 6.1).
- **The hour balance is an append-only ledger.** Never update a balance column; the balance is the sum
  of ledger entries. Every booking, refund, forfeit, expiry and carry-forward is a ledger entry linked
  to its cause.
- **Every state change on bookings, payouts, strikes and verifications writes to `audit_log`** (actor,
  action, entity, before/after).
- **Errors** all use one shape: `{"error": {"code", "message", "details"}}` (`api/app/errors.py`). Raise
  `AppError(status, code, message, details)` for expected failures; `code` is a stable snake_case string
  the web app branches on, `message` is safe to show users. Unhandled errors return a generic 500 and go
  to Sentry; responses never echo submitted values or internal details.
- **Chat** uses polling (every 10 s while a chat is open) in v1. No websockets.
- **Scheduled jobs** are idempotent API endpoints under `/internal/jobs/*`, protected by `JOBS_SECRET`
  and called by a GitHub Actions schedule: pack expiry and carry-forward (daily), strike expiry
  (daily), overdue check-out alerts (every 30 minutes, 6 am–midnight IST — keep each run short to stay
  inside GitHub Actions free minutes) and payouts-due alerts (every 30 minutes, in the same run as overdue check-outs).
  Two runs, `daily` and `frequent`, each a list of tasks in `api/app/services/jobs.py`. Before launch the
  frequent run targets production only, to save Render's shared free hours (README "Scheduled jobs").

---

## 6. Business rules

### 6.1 Hour packs and pricing

- Parents buy hours **per child**. Price = children × hours × tier rate, where the tier depends on hours
  bought **per child**:

  | Hours per child | Rate per child-hour |
  | --- | --- |
  | 1–10 | ₹275 |
  | 11–30 | ₹250 |
  | 31–50 | ₹225 |
  | 51+ | ₹199 |

  Example: 10 hours for 2 children = 2 × 10 × ₹275 = ₹5,500, credited as 20 child-hours.
- A booking uses **duration × number of children** child-hours. 3 hours with 2 children uses 6.
- Every pack expires **30 days after it is credited**. At expiry, unused hours carry forward up to a
  cap set by the pack's tier: 51+ → 10, 31–50 → 5, 11–30 → 2, 1–10 → 0. Carried-forward hours never
  expire. The rest are written off with an `expiry` ledger entry. The cap is **per child**: a 51+
  pack for 2 children carries forward up to 20 child-hours.
- Hours are consumed from the pack that expires soonest first; carried-forward hours are used last.
- Unused hours are never refunded as money.
- Beta purchase flow: parent chooses children and hours, sees the price, pays by UPI to `PACIFY_UPI_ID`,
  enters the UPI reference. The pack is `pending_payment` until an admin confirms the payment, which
  credits the hours. Admins can also reject with a reason.

### 6.2 Sitters and pay

- Each sitter sets an hourly rate between **₹80 and ₹120**, paid **per hour, per child**:
  sitter pay = rate × hours worked × children. 3 hours with 2 children at ₹120 = ₹720.
- Parents never see the sitter's rate. They pay pack rates.
- Pacify's margin = what the parent's consumed child-hours were worth − the sitter's pay. The lowest
  margin is ₹79 per child-hour (51+ pack at ₹199, sitter at ₹120).
- **Hours worked** = check-in to check-out, capped at the booked end time plus approved overtime. A
  sitter who checks in late is paid from check-in. Parents' hours are still debited for the full booking.
- Sitters choose payout by **bank account or UPI**.
- Sitters pay their own travel.

### 6.3 Interviews (introductions)

- Every sitter has an onboarding interview with Pacify before going live.
- Every new parent–sitter pair needs a passed introduction interview before their first booking. Pairs
  with a past completed booking skip it.
- Interviews are free (no hours used). Sitters publish availability; the parent picks an interview slot
  inside it; the API creates a Google Calendar event with a Meet link and invites the parent, the
  sitter and the Pacify interviewer.
- An admin records the outcome: `passed`, `not_passed`, or `no_show`. Only `passed` unlocks booking for
  that pair.

### 6.4 Bookings

- Pacify only takes bookings for children aged **18 months and above**. Child date of birth is required;
  a booking can't include a child under 18 months on the booking date.
- When booking, the parent must say whether home cameras are on and where they are (no cameras in
  bathrooms or changing areas). The sitter sees this before the booking starts.
- Taking the child out of the home needs the parent's permission in the app: the sitter requests it
  during the booking and the parent approves or declines (logged).
- Scheduled in advance only, minimum **2 hours**, durations rounded up to the next **half hour**.
- Bookings are confirmed automatically if the slot is inside the sitter's availability, the sitter
  isn't already booked, the sitter isn't blocked by a strike, the pair is unlocked, both users are
  verified and active, and the parent has enough balance.
- On confirmation, the child-hours are debited (`booking_hold` ledger entry).
- The sitter's availability for that slot is removed.

### 6.5 Cancellations, no-shows and the show-up fee

| Situation | Rule |
| --- | --- |
| Parent cancels ≥ 3 hours before start | Hours refunded. No penalty. |
| Parent cancels < 3 hours before start | Parent loses all booked hours (forfeit). Sitter not paid. |
| Parent not home when sitter arrives | Sitter reports it from the booking screen. Parent loses the booked hours. Pacify pays the sitter a flat **₹100** show-up fee. Admin confirms. |
| Sitter cancels ≥ 8 hours before start | Parent's hours refunded. No penalty. |
| Sitter cancels < 8 hours before start | Parent's hours refunded. Sitter earns nothing and gets a strike. |
| Sitter no-show | Parent reports it, admin confirms. Parent's hours refunded. Sitter earns nothing and gets a strike. |
| Sitter more than 15 minutes late without telling the parent and Pacify | Parent may cancel from the booking screen; it then counts as a sitter no-show. If not cancelled, the sitter is paid only from check-in. |
| Sitter ill | Must tell Pacify and the parent at least 8 hours before (a normal cancellation). With less notice it's a late cancellation and a strike, but an admin can remove the strike if she uploads a doctor's note. |
| Child under 18 months at the booking | Should never happen (bookings are blocked), but if it does: sitter presses Report, isn't required to care for the child and may leave once an adult is with the child. Parent's hours refunded. Pacify pays the sitter **₹100**, no strike. |
| Sitter leaves because she feels unsafe | Only once the child is with a parent or a named adult; she presses Emergency. Once an admin confirms the report, she's paid for the time worked and it's not a strike. |

**Parent not home:** the sitter calls the parent and presses Report; admins try to reach the parent too.
She may leave, and is paid ₹100, only if no parent responds within **20 minutes** of the report (the app
shows a countdown). If a child is there without an adult, she must not leave: the app routes her to the
Emergency button instead.

### 6.6 Strikes

- A strike blocks the sitter from new bookings for: 1st → 24 hours, 2nd → 3 days, 3rd → 1 week,
  4th → 2 weeks, 5th → permanent removal.
- Count only strikes given in the last 6 months; each strike expires 6 months after it was given.
- Existing confirmed bookings stay unless an admin cancels them.
- Admins can add or remove a strike with a reason (audit logged).

### 6.7 Check-in and check-out (codes)

- Each booking has two separate 4-digit codes: a **check-in code** and a **check-out code**. They are
  shown only in the parent's app (no SMS in v1), only on the day of the booking, and each works once.
  The check-out code appears only after check-in.
- **Check-in:** when the sitter arrives, the parent reads out or shows the check-in code; the sitter
  enters it in her app. Her browser location is recorded (if permission is denied, record that and
  still allow check-in).
- **Check-out:** when the parent is home, the parent gives the check-out code; the sitter enters it.
  Location is recorded again. This confirms the child was handed back to a parent.
- Wrong codes: lock code entry for that booking after 5 wrong attempts and alert admins.
- If the parent will be late, the sitter can't check out early; she raises an overtime request (6.8).
- **Overdue check-out:** if a booking isn't checked out 30 minutes after its end time (including approved
  overtime), admins get an email alert and a banner in the admin panel. An admin calls both people and
  can close the booking manually with a reason (audit logged).
- Parents are billed for booked time plus approved overtime. An early check-out doesn't refund hours.
  Sitters are paid for hours worked (6.2).

### 6.8 Overtime

- Overtime must be requested **before** it is worked: the sitter requests extra time (rounded up to the
  next half hour) during the booking, typically when the parent says they'll be late. The parent
  approves or declines in the app.
- Approved overtime is debited from the parent's balance (× children).
- If the balance is short, the shortfall is charged at **₹300 per child per hour** (1 hour short with
  2 children = ₹600) and recorded as an outstanding amount the parent pays by UPI (admin confirms).
  The parent can't make new bookings while they owe money.
- The sitter earns her hourly rate × children for approved overtime she works.

### 6.9 Emergencies and incidents

- Parents and sitters each have an Emergency/Report button on an active booking (sitters' is for their
  own safety too).
- Pressing it creates an incident, emails every address in `ADMIN_ALERT_EMAILS` immediately, and shows
  an alert at the top of the admin panel until acknowledged. An admin then phones both people.
- An open incident holds the sitter's payout for that booking.
- A theft or abuse report suspends the sitter's account immediately until an admin resolves it.

### 6.10 Payouts (beta: manual)

- A sitter's earnings for a booking are released when the booking is checked out with the parent's code
  (or closed by an admin), any overtime request is resolved and there's no open incident.
- **Sitters must be paid within 12 hours** of check-out (or of overtime approval, if later). This is in
  the signed Sitter Terms (2.6).
- The admin panel shows a payouts-due list: each released, unpaid earning (booking, overtime, show-up
  fee, under-18-months fee) with the sitter's bank or UPI details and a countdown to its 12-hour
  deadline. Someone pays it and marks it paid with the transfer reference.
- Admins get an email when a payout has under 3 hours left, and again if it's overdue.
- Sitters see earnings, pending and paid history in their dashboard.

### 6.11 Reviews and chat

- After a completed booking, parent and sitter can each leave a 1–5 rating and short review of the
  other. A sitter's average rating and count show on their profile.
- If a sitter's average over her last 10 bookings falls below **3.5**, flag her for admin review. Before
  removal for ratings, she must be told the reason and given a chance to respond (recorded).
- Communication between families and sitters stays in the in-app chat.
- Chat opens between a parent and sitter once their introduction is scheduled and stays open while they
  have bookings. Admins can read chats when handling an incident (audit logged).

### 6.12 Complaints and grievances

- Help → "Raise a complaint" (and the Report button) creates a complaint, linked to a booking where
  relevant, with a description and optional attachments. Users are asked to report within 24 hours, but
  late complaints are still accepted (flagged as late).
- Admin targets, shown in the admin panel with time remaining: first reply **within 24 hours**, aim to
  resolve **within 48 hours** (serious safety matters up to 15 days, with updates).
- Unresolved after 48 hours, or the user disagrees: escalate to the Grievance Officer (acknowledge within
  24 hours, written decision with reasons within 15 days).
- Appeals against suspension or removal: allowed within 15 days of the decision, reviewed within 7
  working days by an admin not involved in the original decision. The system must stop the original
  decider from handling the appeal.
- Grievance Officer name and contact are config values shown in the app and the terms.

### 6.13 Accounts

- Sitters can close their account once they have no upcoming bookings; all earned amounts are paid out.
- Data access, correction and deletion requests go through the complaint flow (type: data request);
  records the law requires are kept.

---

## 7. Trust and safety (vetting)

**Sitter onboarding steps** (each has a status; the profile goes live only when all pass):
1. Application and profile: photo, date of birth (must be **18+**), bio, years of experience, age
   groups, languages, first-aid certification, home address, hourly rate, payout details (bank account
   or UPI).
   Health disclosure: any serious or long-term condition or allergy that could affect safe care. This is
   health data: store it encrypted, admin-only, access logged, never shown to parents, used only for
   matching. Sitters can update it any time.
2. Government ID upload, plus college or work ID.
3. Police clearance certificate upload.
4. Two references (name, phone, relationship). Admin records the outcome.
5. Psychology test, taken in the app. Questions come from a licensed psychologist and are stored as
   data (`psych_tests`, `psych_questions`); ship with clearly marked placeholder questions until then.
   Admin reviews and records pass/fail.
6. Onboarding interview with Pacify.
7. Admin approval.

**Parent verification:** masked Aadhaar for both parents (the upload screen asks for UIDAI's masked
Aadhaar), a birth certificate per child, then admin approval. Parents can browse after sign-up but
can't request an introduction until approved.

**Document handling:** private bucket, admin-only access, every view logged, birth certificates deleted
automatically once the child is verified (keep status, verifier and date).

**Consent:** before uploading any child documents, the parent must accept the parental consent form
(placeholder text in `/web/src/content/consent.md`, versioned; store which version they accepted and
when). The privacy policy and parent terms ship as placeholders until legal review.

**Terms acceptance (click-wrap, both roles):**
- Documents: Parent terms of service, **Sitter Terms of Use** and the Privacy policy, all versioned, in
  `/web/src/content/`.
- **Sitter Terms of Use v1.1 is final:** `content/sitter-terms-v1.1.md` (move it to
  `/web/src/content/`). **Never change its wording.** Only fill its bracketed placeholders ([DATE],
  LLPIN, registered address, Grievance Officer, Privacy Policy link, emergency line) from config. Don't
  serve it in production while any placeholder is empty.
- Parent terms and Privacy policy are still placeholders marked "DRAFT — NOT LEGALLY REVIEWED".
- Changes to the sitter terms that affect pay or rights must be announced in the app at least **14 days**
  before they take effect (`effective_at`); urgent safety or legal changes can take effect at once.
- At sign-up, after choosing a role, the user sees an unticked checkbox: "I agree to the [Terms of
  service / Sitter Terms of Use] and Privacy policy", with links that open the full text. They can't continue
  until it's ticked and they press the button.
- Record each acceptance: user, document, version, accepted_at, IP address, user agent.
- When a document's version changes, users must accept the new version before their next action that
  matters: parents before booking or buying hours, sitters before taking new bookings. Existing bookings
  are unaffected.
- Aadhaar e-sign for sitters is planned for later (v2 backlog); keep acceptance logic behind one small
  function so a signing method can be added.

**Copy must match reality.** Only claim the checks above: ID check, police verification, references,
interview, psychology test, and meeting before the first booking. Do not claim address verification or
"Pacify Plus" until they exist.

**Company:** Pacifyco LLP. Contact shown in the app: query.pacifyco@gmail.com, +91 8848873841.

---

## 8. Data model (first draft — refine in phase 1, then keep this section in sync)

Tables marked **(created)** exist as models (`api/app/models`) and migrations; the models are the source
of truth for their columns. Other tables are added by the phase that needs them, in its own migration.
Status values use text columns with CHECK constraints (not Postgres enums), so adding a value is a small
migration. Verification statuses are `pending|approved|rejected`.

- `profiles` **(created)** (id = Supabase user id, role, full_name, phone, email, status: `pending|active|suspended|removed`, pin_code, address, lat, lng, created_at)
- `parents` **(created)** (profile_id, second_parent_name, verification_status)
- `children` **(created)** (id, parent_id, name, date_of_birth (18 months+ to be booked), allergies, medical_notes, routines, verification_status)
- `emergency_contacts` **(created)** (id, child_id, name, relationship, phone)
- `sitters` **(created)** (profile_id, date_of_birth, health_disclosure_encrypted, payout_method: `bank|upi`, bank_details_encrypted, bio, years_experience, age_groups[], languages[], first_aid, hourly_rate_paise (CHECK 8000–12000), upi_id, onboarding_status: `in_progress|approved|rejected`, avg_rating, review_count)
- `onboarding_steps` (sitter_id, step, status, notes, reviewed_by, reviewed_at)
- `documents` (id, owner_profile_id, child_id null, type: `aadhaar_masked|birth_certificate|government_id|college_or_work_id|police_certificate|first_aid_certificate|doctor_note|photo`, storage_path, status, deleted_at)
- `document_access_log` (id, document_id, admin_id, accessed_at)
- `consents` (id, parent_id, form_version, accepted_at)
- `legal_documents` (id, kind: `parent_terms|sitter_terms|privacy_policy`, version, published_at, effective_at, content_path)
- `legal_acceptances` (id, profile_id, document_id, method: `clickwrap`, accepted_at, ip_address, user_agent)
- `references` (id, sitter_id, name, phone, relationship, outcome, notes)
- `psych_tests`, `psych_questions`, `psych_attempts`, `psych_answers`
- `availability_slots` (id, sitter_id, starts_at, ends_at)
- `interviews` (id, type: `onboarding|introduction`, sitter_id, parent_id null, starts_at, meet_url, calendar_event_id, outcome, recorded_by)
- `pair_unlocks` (parent_id, sitter_id, unlocked_at, reason: `interview_passed|prior_booking`)
- `packs` (id, parent_id, children_count, hours_per_child, tier_rate_paise, total_paise, units_credited, status: `pending_payment|active|expired|rejected`, upi_reference, credited_at, expires_at, carry_cap_units)
- `ledger_entries` (id, parent_id, pack_id null, booking_id null, kind: `credit|booking_hold|refund|forfeit|overtime|expiry|carry_forward|adjustment`, units (+/−), created_at, created_by)
- `bookings` (id, parent_id, sitter_id, starts_at, ends_at, units_per_child, children_count, status: `confirmed|in_progress|completed|cancelled_parent|cancelled_parent_late|cancelled_sitter|cancelled_sitter_late|parent_absent|sitter_no_show`, check_in_code_hash, check_out_code_hash, code_attempts, codes_locked, checked_in_at, check_in_lat, check_in_lng, checked_out_at, check_out_lat, check_out_lng, closed_by_admin_id, close_reason) — store code hashes, never plain codes; the parent's app gets the code from an endpoint that only the booking's parent can call
- `booking_children` (booking_id, child_id)
- `booking_home_info` (booking_id, cameras_on, camera_locations)
- `outing_requests` (id, booking_id, description, status: `pending|approved|declined`, decided_at)
- `complaints` (id, raised_by, booking_id null, type: `booking|payment|family|sitter|review|suspension|data_request|other`, description, status: `open|replied|resolved|escalated|appealed|closed`, late, first_reply_at, resolved_at, assigned_to, decided_by)
- `overtime_requests` (id, booking_id, units, status: `pending|approved|declined`, decided_at)
- `outstanding_dues` (id, parent_id, booking_id, amount_paise, status, upi_reference)
- `strikes` (id, sitter_id, booking_id, reason, given_at, expires_at, removed_by null, removal_reason, doctor_note_document_id null)
- `incidents` (id, booking_id, raised_by, status: `open|acknowledged|resolved`, notes)
- `messages` (id, parent_id, sitter_id, sender_id, body, created_at)
- `reviews` (id, booking_id, author_id, subject_id, rating, body)
- `sitter_earnings` (id, sitter_id, booking_id null, kind: `booking|overtime|show_up_fee|under_age_fee`, amount_paise, status: `held|released|paid`, due_by, payout_id null)
- `payouts` (id, sitter_id, amount_paise, method: `bank|upi`, transfer_reference, paid_by, paid_at)
- `audit_log` **(created)** (id, actor_id, action, entity, entity_id, before, after, created_at)
- `service_area_pincodes` **(created)** (pin_code, active) — seeded with the launch pin codes

---

## 9. Features and required tests

Automated tests are required for every item. API tests use pytest against a real Postgres (Docker in
CI, not mocks). Web tests use Vitest + Testing Library. Add Playwright smoke tests for the main journeys
in the beta phase.

| Feature | Required tests |
| --- | --- |
| Auth and roles | JWT verified; wrong role gets 403 on every role-gated endpoint; suspended/removed users blocked |
| Service area | Sign-up and booking rejected outside listed pin codes |
| Consent | Child document upload refused without an accepted consent of the current version |
| Terms click-wrap | Sign-up can't complete without acceptance; acceptance stores version, time, IP and user agent; parent can't book or buy and sitter can't take bookings until the latest version is accepted; parents see parent terms and sitters see the Sitter Terms of Use |
| Documents | Non-admins can't get a signed view URL; every admin view logged; birth certificate deleted after child verification |
| Sitter onboarding | Profile not searchable until every step passes; rate outside ₹80–120 rejected |
| Search and filters | Only active, verified, unblocked sitters returned; distance sort; each filter works; parent never sees sitter rate |
| Interviews | Slot must be inside sitter availability; Calendar call mocked and event stored; only `passed` unlocks the pair; prior completed booking unlocks |
| Packs and pricing | Tier boundaries (10, 11, 30, 31, 50, 51 hours); per-child price; pending pack credits nothing; admin confirm credits units |
| Ledger | Balance = sum of entries; no negative balance; consumption order (soonest-expiring first, carried-forward last) |
| Expiry job | 30-day expiry; carry cap per tier and per child; carried hours never expire; job is idempotent |
| Bookings | Min 2 hours; half-hour rounding; double-booking prevented (including concurrent requests); blocked sitter can't be booked; insufficient balance rejected; children × duration debited |
| Cancellations | Each row of the 6.5 table, including exact 3-hour and 8-hour boundaries |
| Strikes | Ladder 24h / 3d / 1w / 2w / removal; only last-6-month strikes count |
| Check-in/out codes | Codes visible only to the booking's parent and only on the booking day; check-out code only after check-in; codes don't work for other bookings or twice; wrong codes rejected and locked after 5 attempts; locations stored; overdue check-out alert after end + 30 min; admin manual close audit logged; early check-out doesn't refund |
| Overtime | Only during an in-progress booking; parent approval required; balance debit; shortfall at ₹300 per child per hour creates a due; dues block new bookings |
| Incidents | Email sent to every admin address (mocked); payout held while open |
| Sitter pay | Rate × hours worked × children; hours worked = check-in to check-out capped at booked end + approved overtime; late check-in paid from check-in |
| Payouts | Earnings released only after checkout + overtime resolved + no open incident; due within 12 hours; alerts at 3 hours left and when overdue; ₹100 show-up and under-18-months fees; bank or UPI; mark-paid records reference |
| Reviews | Only after a completed booking, once per author per booking; average updates; flag when last-10 average < 3.5 |
| Child age and home info | Child under 18 months can't be booked; camera declaration required; outing needs parent approval |
| New cancellation rows | 15-minute late rule; 20-minute parent-not-home wait; under-18-months: parent refunded, sitter ₹100, no strike; unsafe early exit paid for time worked with no strike after admin confirms; doctor's note strike removal |
| Complaints | SLA timers; escalation; original decider can't handle the appeal; late complaints flagged |
| Sitter terms | Wording matches `sitter-terms-v1.1.md`; placeholders filled from config; production refuses to serve it with an empty placeholder |
| Sitter onboarding extras | Under-18 rejected; health disclosure admin-only and access logged |
| Chat | Only between unlocked pairs; admin read is audit logged |
| Audit | State changes on bookings, payouts, strikes and verifications write audit rows |

### Security testing (owned by Claude Code, phase 12)

Check and add tests for: authorisation on every endpoint (IDOR — a user can never read or change
another user's data by changing an id), RLS denies direct table access with the anon key, storage
buckets not publicly readable, signed URL expiry, input validation and size limits on uploads (type and
size), rate limiting on auth and booking endpoints, CORS limited to our web origins, secure headers,
no secrets in the repo or logs, dependency audit (`pip-audit`, `npm audit`), and that jobs endpoints
reject requests without `JOBS_SECRET`.

---

## 10. Out of scope for v1

Aadhaar e-sign for the sitter terms, native apps, live location tracking, WhatsApp/SMS notifications, recurring bookings, automated payouts,
Razorpay, other care types, Pacify Plus, AI features.
