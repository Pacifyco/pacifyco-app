# CLAUDE.md — Pacifyco build guide

Read this file and `progress.md` at the start of every session. Read `design.md` before any UI work.
Do not re-read the whole codebase to find your place: `progress.md` says where we are.

---

## 1. What Pacifyco is

Pacify (company: Pacifyco) is a babysitter marketplace for parents in Bengaluru. Parents browse vetted
sitter profiles and book scheduled care, paid by the hour at the plan the parent picks (a short first
booking with the parent at home is encouraged with a new sitter). Pacify vets everyone, can suspend or remove any user,
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
    /routers    one router per area: auth, profiles, documents, sitters, search,
                payments, bookings, overtime, checkins, incidents, chat, reviews,
                payouts, admin, jobs
    /services   business rules (pricing, payments, cancellations, strikes, payouts)
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

API: `ENVIRONMENT`, `DATABASE_URL`, `MIGRATION_DATABASE_URL` (CI only), `SUPABASE_URL`, `SUPABASE_JWKS_URL` (optional; defaults
from `SUPABASE_URL`), `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`, `EMAIL_FROM`,
`ADMIN_ALERT_EMAILS`, `SENTRY_DSN`,
`JOBS_SECRET`, `PUBLIC_WEB_URL`, `CORS_ORIGINS`, `PACIFY_UPI_ID`.

Web: `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_SENTRY_DSN`,
`VITE_ENVIRONMENT`, and the Sitter Terms values `VITE_PACIFY_LLPIN`, `VITE_PACIFY_REGISTERED_ADDRESS`,
`VITE_GRIEVANCE_OFFICER_NAME`, `VITE_GRIEVANCE_OFFICER_EMAIL`, `VITE_GRIEVANCE_OFFICER_PHONE`,
`VITE_EMERGENCY_LINE`, `VITE_SITTER_TERMS_DATE`, `VITE_FAMILY_TERMS_DATE`, `VITE_FAMILY_INTRO_FEE`.

---

## 5. Architecture decisions

- **All writes and business logic go through the FastAPI API.** The web app uses Supabase only for
  sign-in (email OTP and Google). The API verifies the Supabase JWT on every request and loads the
  user's role from the `profiles` table (`api/app/auth.py`). Supabase projects use asymmetric JWT
  signing keys, checked against the project's JWKS, so the API holds no JWT secret.
- **Role gates:** role-only endpoints go in `routers/parents.py`, `sitters.py` or `admin.py`, whose
  routers require that role (`require_role`: wrong role 403 `forbidden`; suspended or removed 403
  `account_blocked`). Any other endpoint must be listed in `PUBLIC` in `tests/test_roles.py`, which
  fails otherwise. The web app wraps each area in `RequireRole`; the API is what enforces it.
- **Row Level Security on every table** with no policies for the `anon` and `authenticated` roles, so
  the database can't be read directly from the browser even by mistake. The API connects with its own
  database role, `pacifyco_api` (BYPASSRLS; reads and writes rows, can't change tables; `audit_log` is
  insert-only). Migrations run as the database owner. New tables get the API's grants automatically;
  new append-only tables must revoke UPDATE and DELETE in their migration.
- **Sentry collects errors only** (no tracing, replay or logs) and no personal data: user info, cookies,
  headers, request bodies, query strings and local variables are all off in both SDKs.
- **Storage buckets are private.** Uploads go through signed upload URLs issued by the API. Files are
  viewed only by admins through short-lived signed URLs, and every view writes a row to
  `document_access_log`. One exception (decided 2026-11-09): a live sitter's profile photo (JPG or PNG)
  is shown to parents through short-lived signed URLs on her card and profile page (not logged).
- **Money** is stored as integer paise. **Time** is stored in UTC (`timestamptz`) and shown in
  Asia/Kolkata.
- **Booked time** is stored as integer hours ("units"); bookings and overtime are both whole hours
  only, no half-hours (decided 2026-11-03).
- **Money owed and paid is append-only.** Every booking payment, overtime charge, refund and
  cancellation charge is a row linked to its booking (`payments`); never edit an amount in place.
- **Every state change on bookings, payouts, strikes and verifications writes to `audit_log`** (actor,
  action, entity, before/after).
- **Errors** all use one shape: `{"error": {"code", "message", "details"}}` (`api/app/errors.py`). Raise
  `AppError(status, code, message, details)` for expected failures; `code` is a stable snake_case string
  the web app branches on, `message` is safe to show users. Unhandled errors return a generic 500 and go
  to Sentry; responses never echo submitted values or internal details.
- **Chat** uses polling (every 10 s while a chat is open) in v1. No websockets.
- **Scheduled jobs** are idempotent API endpoints under `/internal/jobs/*`, protected by `JOBS_SECRET`
  and called by a GitHub Actions schedule: strike expiry
  (daily), overdue check-out alerts (every 30 minutes, 6 am–midnight IST — keep each run short to stay
  inside GitHub Actions free minutes), payouts-due alerts (every 30 minutes, in the same run as overdue
  check-outs), and auto-cancelling `pending_payment` bookings once their 3-hour payment deadline passes
  (6.1; same frequent run).
  Two runs, `daily` and `frequent`, each a list of tasks in `api/app/services/jobs.py`. Before launch the
  frequent run targets production only, to save Render's shared free hours (README "Scheduled jobs").

---

## 6. Business rules

### 6.1 Plans and pricing (decided 2026-11-03; replaces hour packs)

- The parent picks a **plan for each booking** and pays by the hour. There are no hour packs, balances
  or expiry.

  | Plan | Price per hour | Children | Latest end (overtime included) | Bath time | Outings |
  | --- | --- | --- | --- | --- | --- |
  | Pause | ₹499 | one child only | 6 pm | no | no |
  | Unwind | ₹699 for the first child, +₹150 per extra child (2 children = ₹849) | any number | 10:30 pm | can be ticked | no |
  | Recharge | ₹899 for any number of children | any number | 12 am (midnight) | can be ticked | yes, with the parent's approval |

- **Children on a booking (decided 2026-11-09):** a booking starts as one child, whatever the number
  of verified children on the account; the parent adds each extra child who'll be there. Pause takes
  one child only (Pause sitters are still shown to every parent). Unwind adds ₹150/hour per extra child.
  Recharge costs the same for any number, but parents still add every child so the sitter knows who
  she's caring for. Only the parent's own children can be added, and the booking is confirmed only
  once each of them is verified (6.4).
- Booking price = the plan's hourly price (for that number of children) × booked hours. Example:
  Recharge, 3 hours = ₹2,697. No GST for now.
- Booked time is counted in **whole hours only** (no half-hours); no minimum length; no earliest start
  time. (Decided 2026-11-03, replaces half-hour rounding.)
- **No match deposit.** (Decided 2026-11-03; the idea is dropped.) The parent pays the full price up
  front. Product flow: parents are encouraged to make a short first (e.g. 1-hour) booking with a new
  sitter to assess fit before booking longer sessions — a UX nudge, not an enforced rule.
- **Paying for a booking (beta, manual UPI):** the parent picks the plan, children and hours, sees the
  full price, and pays all of it by UPI to `PACIFY_UPI_ID`, entering the UPI reference. The booking is
  `pending_payment` until an admin confirms the payment, then it's `confirmed`. Admins can reject with a
  reason.
- **Payment deadline:** if payment isn't confirmed by **3 hours before the booking's start**, the
  `pending_payment` booking is auto-cancelled (same boundary as the parent late-cancellation rule in
  6.5). Decided 2026-11-03 — parents should pay as soon as they book, since slots aren't held (6.4).
- Refunds are money, paid back by UPI or bank transfer (beta: manual, recorded with a reference).
- Plan prices appear when the parent picks a plan; sitter cards never show a price.

### 6.2 Sitter levels and pay

- Every sitter has a **level**, set by an admin (new sitters too: admins decide where each starts and
  move sitters up when they meet the conditions). A sitter works **only her own level's plan**:

  | Level | Works | Pay per hour | Guide for admins |
  | --- | --- | --- | --- |
  | Pause (Level 1) | Pause bookings | ₹200 | 0–1 families; can be new to babysitting |
  | Unwind (Level 2) | Unwind bookings | ₹300 | 2 families |
  | Recharge (Level 3) | Recharge bookings | ₹400 | 3+ families; her reference (name, phone, relationship) is shown to parents, with her consent — a tick in her sitter application (decided 2026-11-03) |

- Pay is per hour, **the same whatever the number of children**. Sitters aren't told the plan name. The
  app tells them: "Based on the experience we understand you have, you'll be paid ₹[pay] an hour. As
  you put in more hours, we'll increase your pay."
- Sitter pay = level pay × hours worked, plus overtime (6.8). Sitters don't set a rate.
- **Hours worked** = check-in to the booked end time. A sitter who checks in late is paid from
  check-in; the parent still pays for the full booking.
- Sitters choose payout by **bank account or UPI**.
- Sitters pay their own travel.

### 6.3 First booking with a new sitter (replaces interviews, decided 2026-11-08)

- **No interviews.** There is no sitter onboarding interview and no parent–sitter introduction (no
  Google Meet, no Google Calendar). A verified parent can book any live sitter of the plan's level
  straight away; there is no pair-unlock step.
- Parents are **asked** to make their first booking with a new sitter a **1-hour booking with a parent
  at home**, to see if the sitter suits them. This is a nudge on the booking screen, not enforced:
  longer first bookings are allowed.

### 6.4 Bookings

- Pacify only takes bookings for children aged **18 months and above**. Child date of birth is required;
  a booking can't include a child under 18 months on the booking date.
- When booking, the parent must say whether home cameras are on and where they are (no cameras in
  bathrooms or changing areas). The sitter sees this before the booking starts.
- Taking the child out of the home needs the parent's permission in the app: the sitter requests it
  during the booking and the parent approves or declines (logged).
- Scheduled in advance only, with a plan (6.1). Pause takes one child only. The booking must end by the
  plan's latest end time, overtime included.
- Bath time is ticked when booking (Unwind and Recharge only). Outings are allowed only on Recharge,
  still approved by the parent during the booking (above).
- **Sitter availability (decided 2026-11-09):** a sitter sets her usual week once (whole-hour times per
  weekday, India time) and it repeats every week until she changes it; she marks single **days off**.
  Her free times are worked out from these for the next **14 days**, which is also how far ahead
  parents can book.
- A booking can be made if the slot is inside the sitter's availability, the sitter's level matches
  the plan, she isn't already booked or blocked by a strike, the sitter is live (7), the parent has
  finished their profile (6.13) and is active, and the parent owes nothing. It's `pending_payment`
  until the payment is confirmed (6.1), then `confirmed`.
- **A booking is only confirmed once every child on it is verified** (birth certificate reviewed and
  approved by an admin, 7), as well as paid. Decided 2026-11-08: parents can book before that review
  is done; the booking waits until it is. Until it's confirmed, the booking doesn't show on the
  sitter's side (her bookings and schedule); she only sees confirmed bookings.
- **No slot hold while payment is pending** (decided 2026-11-03): the sitter's availability for that
  slot is only removed once a booking is `confirmed`. More than one parent can have a `pending_payment`
  booking for the same slot at once — whoever's payment is confirmed first wins it; any other
  `pending_payment` booking for an overlapping slot is then auto-cancelled (the parent is told).

### 6.5 Cancellations, no-shows and the show-up fee

| Situation | Rule |
| --- | --- |
| Parent cancels ≥ 3 hours before start | Money refunded. No penalty. |
| Parent cancels < 3 hours before start | Parent pays for the whole booking (no refund). Sitter not paid. |
| Parent not home when sitter arrives | Sitter reports it from the booking screen. Parent pays for the whole booking. Pacify pays the sitter **₹100 per booked hour** (show-up fee). Admin confirms. |
| Sitter cancels ≥ 8 hours before start | Parent's money refunded. No penalty. |
| Sitter cancels < 8 hours before start | Parent's money refunded. Sitter earns nothing and gets a strike. |
| Sitter no-show | Parent reports it, admin confirms. Parent's money refunded. Sitter earns nothing and gets a strike. |
| Sitter more than 15 minutes late without telling the parent and Pacify | Parent may cancel from the booking screen; it then counts as a sitter no-show. If not cancelled, the sitter is paid only from check-in. |
| Sitter ill | Must tell Pacify and the parent at least 8 hours before (a normal cancellation). With less notice it's a late cancellation and a strike, but an admin can remove the strike if she uploads a doctor's note. |
| Child under 18 months at the booking | Should never happen (bookings are blocked), but if it does: sitter presses Report, isn't required to care for the child and may leave once an adult is with the child. Parent is charged for 1 hour; the rest is refunded. Sitter is paid for that 1 hour (her level pay); no strike. (Decided 2026-11-03.) |
| Only adult at home is a man (decided 2026-11-12) | The sitter may decline the booking on the spot and reports it with the Issues button (6.9). Parent pays for the whole booking (no refund, as in the Family Terms). No strike; Pacify pays the sitter a **flat ₹100**. |
| Sitter leaves because she feels unsafe | Only once the child is with a parent or a named adult; she presses Emergency. Once an admin confirms the report, she's paid for the time worked and it's not a strike. |

**Parent not home:** the sitter calls the parent and presses Report; admins try to reach the parent too.
She may leave, and is paid the show-up fee, only if no parent responds within **20 minutes** of the report (the app
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
- If the parent is late, the sitter can't check out early; she waits, and the extra time becomes
  overtime at check-out (6.8).
- **Overdue check-out:** if a booking isn't checked out 30 minutes after its end time, admins get an email alert and a banner in the admin panel. An admin calls both people and
  can close the booking manually with a reason (audit logged).
- Parents pay for the booked time plus overtime. An early check-out refunds nothing. Sitters are paid
  for hours worked (6.2).

### 6.8 Overtime

- **Overtime request (decided 2026-11-12):** during the booking the parent presses "Request overtime"
  and picks a number of **whole hours**; the sitter gets a notification and accepts (they're assumed to
  have agreed it between them) or declines. Nothing is charged when she accepts.
- Overtime is always worked out **at check-out**, whether or not a request was accepted (a parent who is
  simply late still pays): if the check-out time is past the booked end time, the extra time is
  **rounded up to the next full hour** and charged at the booking's plan price per hour.
- It's charged right away. Beta: the parent is shown a UPI payment link or QR for the amount, payable
  within **2 hours**, and enters the UPI reference; an admin confirms. Until it's paid, it's an
  outstanding amount and the parent can't make new bookings.
- The sitter earns her level pay for the same rounded-up overtime hours.
- **Running past the plan's latest end time** (decided 2026-11-03): the sitter still can't leave the
  child. Overtime hours that fall after the plan's latest end (6 pm Pause / 10:30 pm Unwind / 12 am
  Recharge) are charged at the **next tier's** hourly rate instead of the current plan's (Pause overage
  → Unwind rate, Unwind overage → Recharge rate); the sitter is still paid her own level pay for the
  hours she works. Recharge has no higher tier: for now, overage past midnight on Recharge is charged
  at the Recharge rate itself (deferred default, decided 2026-11-03 — revisit if it comes up in
  practice; see `progress.md`).

### 6.9 Emergencies and incidents

- Parents and sitters each have an Emergency/Report button on an active booking (sitters' is for their
  own safety too).
- **Issues button (decided 2026-11-12):** separate from Emergency, parents and sitters can report a
  non-emergency issue from the booking screen, e.g. running late, or the only adult at home being a
  man (6.5). It goes to admins (a complaint linked to the booking, 6.12).
- Pressing it creates an incident, emails every address in `ADMIN_ALERT_EMAILS` immediately, and shows
  an alert at the top of the admin panel until acknowledged. An admin then phones both people.
- An open incident holds the sitter's payout for that booking.
- A theft or abuse report suspends the sitter's account immediately until an admin resolves it. A
  confirmed theft normally ends in removal (the sitter consent says "permanent removal and a police
  complaint"; decided 2026-11-12).

### 6.10 Payouts (beta: manual)

- A sitter's earnings for a booking are released when the booking is checked out with the parent's code
  (or closed by an admin), any overtime request is resolved and there's no open incident.
- **Sitters must be paid within 12 hours** of check-out (or of overtime approval, if later). This is in
  the signed Sitter Terms (2.6).
- The admin panel shows a payouts-due list: each released, unpaid earning (booking, overtime, show-up
  fee) with the sitter's bank or UPI details and a countdown to its 12-hour
  deadline. Someone pays it and marks it paid with the transfer reference.
- Admins get an email when a payout has under 3 hours left, and again if it's overdue.
- Sitters see earnings, pending and paid history in their dashboard.

### 6.11 Reviews and chat

- After a completed booking, parent and sitter can each leave a 1–5 rating and short review of the
  other. A sitter's average rating and count show on their profile.
- If a sitter's average over her last 10 bookings falls below **3.5**, flag her for admin review. Before
  removal for ratings, she must be told the reason and given a chance to respond (recorded).
- Pacify connects families and sitters through the in-app chat, and sitters never have to share their
  number. After the first booking they may choose to exchange numbers; the app doesn't stop it
  (decided 2026-11-12).
- Medicine: a sitter gives medicine only if the parent has written the instructions in the app. For
  now that's the child's medical notes (`children.medical_notes`); no separate medicine field (decided
  2026-11-12).
- Potty training and diaper changes are agreed between parent and sitter, not through a booking field:
  in the in-app chat or in person at the 1-hour first booking (decided 2026-11-12).
- Chat opens between a parent and sitter once they have a confirmed booking (no messaging before
  booking; decided 2026-11-08) and stays open while they have bookings. Admins can read chats when
  handling an incident (audit logged).

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

- **Sign-up flow (decided 2026-11-08, replaces the long sign-up form):** on their first sign-in a
  person chooses **parent** or **sitter** and confirms it ("You're joining as a parent. Is that right?").
  They then go **straight into their area** of the app. Everything else (full name, Indian mobile
  number, home pin code and address, the consent page with the terms (7; moved off sign-up 2026-11-12),
  family details, the sitter application) is asked for there as "finish your profile" prompts. Parents can't book until
  their profile is finished; sitters don't appear to parents until theirs is finished and approved (7).
  The service-area pin code check (1) moves to where the pin code is entered, and still applies before
  booking. Admin accounts are never chosen at sign-up; they are created with the CLI
  (`python -m app.cli create-admin`).
- Users can't change their own role. An admin can change it only while the account is empty (no
  children, documents, onboarding steps, payments or bookings), and the change is audit logged.
- One email = one account = one role. Someone who is both a parent and a sitter uses two accounts with
  different emails, each verified separately.
- Sitters can close their account once they have no upcoming bookings; all earned amounts are paid out.
- Data access, correction and deletion requests go through the complaint flow (type: data request);
  records the law requires are kept.

---

## 7. Trust and safety (vetting)

**Sitter onboarding steps** (each has a status; the profile goes live only when all pass):
1. Application and profile: photo, date of birth (must be **18+**), bio, years of experience, age
   groups, languages, first-aid certification, home address, payout details (bank account or UPI).
   Health disclosure: any serious or long-term condition or allergy that could affect safe care. This is
   health data: store it encrypted, admin-only, access logged, never shown to parents, used only for
   matching. Sitters can update it any time.
2. Government ID upload, plus college or work ID.
3. Police clearance certificate upload.
4. Two references (name, phone, relationship). Admin records the outcome.
5. Psychology test, taken in the app: multiple-choice questions plus a few short written answers; an
   admin reads them and records pass or fail. After a fail, she can take it again only once an admin
   allows a retake (decided 2026-11-08; audit logged). Questions come from a licensed psychologist and are stored as
   data (`psych_tests`, `psych_questions`); ship with clearly marked placeholder questions until then.
   Admin reviews and records pass/fail.
6. Admin approval, with the sitter's level set (6.2). (The onboarding interview was dropped
   2026-11-08.) Only then is she live: shown to parents and bookable.

**Parent verification:** a birth certificate per child, reviewed and approved by an admin. The family
(parent) is verified once **every** child's certificate is approved; adding a child sets the family back
to waiting until that child is approved (decided 2026-11-08). Parents can browse and book once their
profile is finished, but a booking is only confirmed once every child on it is verified (6.4). Once a
child is verified, its name and date of birth are locked (the parent asks Pacify to change them); the
parent can still add more children. A rejected certificate is kept until the parent uploads a new one. **No ID document is collected from parents**
(decided 2026-11-03, Reuben: "we will not be taking aadhaar details anymore" — drops the masked-Aadhaar
upload entirely, and with it the single-parent declaration that existed only to stand in for a second
Aadhaar). What, if anything, replaces a parent-identity check is an open question in `progress.md`.

**Document handling:** private bucket, admin-only access, every view logged, birth certificates deleted
automatically once the child is verified (keep status, verifier and date). Sitters' profile photos are
the one exception: parents see a live sitter's photo (section 5).

**Rejections (decided 2026-11-09):** an admin who rejects anything (a birth certificate, an onboarding
step, a reference, the psychology test or a whole application) must give a rejection reason, which
the parent or sitter sees; admin notes stay internal. A new upload or change after a rejection sends
that item back for review (birth certificates and sitter steps 1-4). The psychology test is the
exception: after a fail, an admin decides when she can retake it.

**Consent (decided 2026-11-02, follow Family Terms 11.2):** at parent sign-up, separate unticked boxes,
nothing pre-ticked, each recorded with its version and time:
1. **Required:** use of the parent's own data for the account, verification, bookings, payments and safety.
2. **Required:** use of each child's data, given as parent or guardian, to match and brief a sitter and
   keep the child safe.
3. **Required:** sharing the child's care details with the booked sitter.
4. **Required:** emergency authorisation (if the parent and emergency contacts can't be reached, the
   sitter may call 112 and take the child to the nearest hospital or doctor, and Pacifyco may share the
   child's health details with treating doctors).
5. **Optional:** offers and updates from Pacifyco; saying no changes nothing, and it can be withdrawn.

The labels use the wording of Family Terms 11.2. These replace the single parental consent form built in
phase 2 (`/parent/consent`); child documents still need every required consent at its current version.

**Emergency contacts and authorised adults (decided 2026-11-02, follow Family Terms 2.5):** two emergency
contacts per **family** (not per child), and any number of named **authorised adults** who may hand over or
receive the child during a booking. The parent confirms they have each person's permission to share their
details.

**Uploads:** PDF, JPG or PNG only, at most 5 MB each, checked by the API (type from the file's contents,
not its name).

**Terms acceptance (click-wrap, both roles):**
- Documents: Parent terms of service, **Sitter Terms of Use**, the **sitter consent** and the Privacy policy, all versioned, in
  `/web/src/content/`.
- **Sitter Terms of Use v1.1 is final:** `web/src/content/sitter-terms-v1.1.md` (a test checks its
  wording against a fingerprint). Placeholders are filled in `web/src/lib/legal.ts` from the
  `VITE_PACIFY_*`, `VITE_GRIEVANCE_OFFICER_*`, `VITE_EMERGENCY_LINE` and `VITE_SITTER_TERMS_DATE`
  variables. **Never change its wording.** Only fill its bracketed placeholders ([DATE],
  LLPIN, registered address, Grievance Officer, Privacy Policy link, emergency line) from config. Don't
  serve it in production while any placeholder is empty.
- **Family Terms of Use v1.0 is final** (the parent terms): `web/src/content/family-terms-v1.0.md`,
  converted word for word from Reuben's .docx and fingerprinted the same way. Same placeholders as the
  sitter terms plus its own date (`VITE_FAMILY_TERMS_DATE`) and the introduction fee in 7.2
  (`VITE_FAMILY_INTRO_FEE`). Where it differs from the rules in this file, the "Open questions" in
  `progress.md` list each difference; don't change either side until Reuben decides.
- The Privacy policy is still a placeholder marked "DRAFT — NOT LEGALLY REVIEWED".
- Changes to the sitter terms that affect pay or rights must be announced in the app at least **14 days**
  before they take effect (`effective_at`); urgent safety or legal changes can take effect at once.
- **On the consent page, not at sign-up (decided 2026-11-12, Reuben):** the user sees an unticked
  checkbox: "I agree to the [Family Terms of Use / Sitter Terms of Use] and Privacy policy", with links
  that open the full text. Parents: on the parental consent page (`/parent/consent`), beside the consents,
  all saved together. Sitters: on the **sitter consent** page (`/sitter/consent`), below the sitter consent
  (`web/src/content/sitter-consent-v1.0.md`, Reuben's "Sitter consent" document word for word, fingerprinted
  like the terms) with its own tick ("I've read these and I'll follow them"). The sitter consent is a
  versioned legal document (`sitter_consent`) accepted the same way. Nothing in the area is blocked until
  then, but the profile isn't finished: parents can't book, and admins can't approve a sitter.
- Record each acceptance: user, document, version, accepted_at, IP address, user agent.
- When a document's version changes, users must accept the new version before their next action that
  matters: parents before booking or buying hours, sitters before taking new bookings. Existing bookings
  are unaffected. The consent step on their profile checklist goes back to "to do" and the consent page
  asks for just the new version.
- Aadhaar e-sign for sitters is planned for later (v2 backlog); keep acceptance logic behind one small
  function so a signing method can be added.

**Copy must match reality.** Only claim the checks above: ID check, police verification, references
and psychology test. Don't claim an interview or a meeting before the first booking (both dropped
2026-11-08). Do not claim address verification or
"Pacify Plus" until they exist.

**Company:** Pacifyco LLP. Contact shown in the app: query.pacifyco@gmail.com, +91 8848873841.

---

## 8. Data model (first draft — refine in phase 1, then keep this section in sync)

Tables marked **(created)** exist as models (`api/app/models`) and migrations; the models are the source
of truth for their columns. Other tables are added by the phase that needs them, in its own migration.
Status values use text columns with CHECK constraints (not Postgres enums), so adding a value is a small
migration. Verification statuses are `pending|approved|rejected`.

- `profiles` **(created)** (id = Supabase user id, role, full_name (empty until filled in after sign-up, 6.13), phone, email, status: `pending|active|suspended|removed`, pin_code, address, lat, lng, created_at)
- `parents` **(created)** (profile_id, second_parent_name, verification_status)
- `children` **(created)** (id, parent_id, name, date_of_birth (18 months+ to be booked), allergies, medical_notes, routines, verification_status, verified_by, verified_at, verification_notes) — name and date of birth locked once verified
- `emergency_contacts` **(created)** (id, parent_id, name, relationship, phone) — exactly two per family
- `authorised_adults` **(created)** (id, parent_id, name, relationship, phone)
- `sitters` **(created)** (profile_id, date_of_birth, health_disclosure_encrypted, payout_method: `bank|upi`, bank_details_encrypted, bio, years_experience, age_groups[], languages[], first_aid, upi_id, onboarding_status: `in_progress|approved|rejected`, level `pause|unwind|recharge` (null until an admin sets it), reference_shared_consent, avg_rating, review_count) — no rate column (dropped 2026-11-03)
- `onboarding_steps` **(created)** (sitter_id, step: `profile|identity_documents|police_certificate`, status, notes, reviewed_by, reviewed_at) — admin reviews of steps 1-3; references and the psych test keep their own outcomes; `app/services/verification.py` combines them. Health disclosure views are logged in `audit_log` (`health_disclosure_viewed`)
- `documents` **(created)** (id, owner_profile_id, child_id null, type: `birth_certificate|government_id|college_or_work_id|police_certificate|first_aid_certificate|doctor_note|photo`, storage_path, status, deleted_at) — no `aadhaar_masked` (dropped 2026-11-03)
- `document_access_log` **(created)** (id, document_id, admin_id, accessed_at)
- `consents` **(created)** one row per consent kind (`own_data|child_data|share_care_details|emergency_authorisation|marketing`)
  and version, with marketing withdrawable — append-only, one row per parent per version; current version is `CONSENT_VERSION` in `api/app/services/consent.py`, matching the `version:` line of `web/src/content/consent.md`. No `single_parent_declaration` kind (dropped 2026-11-03 with Aadhaar)
- `legal_documents` **(created)** (id, kind: `parent_terms|sitter_terms|privacy_policy|sitter_consent`, version, published_at, effective_at, content_path) — read-only for the API; a new version is a migration that adds a row (plus the new text in `web/src/content/` with the same version; a test checks they match). The current version is the latest whose `effective_at` has passed, so pay or rights changes to the sitter terms get an `effective_at` 14+ days out
- `legal_acceptances` **(created)** (id, profile_id, document_id, method: `clickwrap`, accepted_at, ip_address, user_agent) — append-only; written only by `record_acceptances` in `api/app/services/legal.py`; `require_current_terms` gates booking, buying hours and taking bookings
- `references` **(created)** (id, sitter_id, name, phone, relationship, outcome, notes)
- `psych_tests`, `psych_questions`, `psych_attempts`, `psych_answers` **(created)**
- `weekly_hours` **(created)** (id, sitter_id, weekday 0=Monday, start_hour 0-23, end_hour 1-24) — her usual week, repeating; times on a day may touch but not overlap. `days_off` **(created)** (sitter_id, day). Replaced `availability_slots` (dated times, dropped 2026-11-09). Free times are worked out, not stored (`app/services/availability.py`)
- `geocode_cache` **(created)** (query, lat, lng) — Nominatim results (`app/services/geocoding.py`); a profile's
  lat/lng are looked up when its address is saved
- `payments` (id, booking_id, parent_id, kind: `booking|overtime|refund|cancellation_charge`, amount_paise (+ owed or paid by the parent, − refunded), status: `pending|confirmed|rejected`, upi_reference, due_by, confirmed_by, confirmed_at, created_at) — append-only; replaces packs and the hour ledger. No match deposit (dropped 2026-11-03)
- `bookings` (id, parent_id, sitter_id, starts_at, ends_at, plan: `pause|unwind|recharge`, units, children_count, price_paise, bath_time, status: `pending_payment|confirmed|in_progress|completed|cancelled_parent|cancelled_parent_late|cancelled_sitter|cancelled_sitter_late|parent_absent|sitter_no_show`, check_in_code_hash, check_out_code_hash, code_attempts, codes_locked, checked_in_at, check_in_lat, check_in_lng, checked_out_at, check_out_lat, check_out_lng, closed_by_admin_id, close_reason) — store code hashes, never plain codes; the parent's app gets the code from an endpoint that only the booking's parent can call
- `booking_children` (booking_id, child_id)
- `booking_home_info` (booking_id, cameras_on, camera_locations)
- `outing_requests` (id, booking_id, description, status: `pending|approved|declined`, decided_at)
- `complaints` (id, raised_by, booking_id null, type: `booking|payment|family|sitter|review|suspension|data_request|other`, description, status: `open|replied|resolved|escalated|appealed|closed`, late, first_reply_at, resolved_at, assigned_to, decided_by)
- `overtime_charges` (id, booking_id, minutes_over, hours_charged (rounded up), amount_paise, sitter_pay_paise, created_at) — computed at check-out (6.8); its payment is a `payments` row
- `strikes` (id, sitter_id, booking_id, reason, given_at, expires_at, removed_by null, removal_reason, doctor_note_document_id null)
- `incidents` (id, booking_id, raised_by, status: `open|acknowledged|resolved`, notes)
- `messages` (id, parent_id, sitter_id, sender_id, body, created_at)
- `reviews` (id, booking_id, author_id, subject_id, rating, body)
- `sitter_earnings` (id, sitter_id, booking_id null, kind: `booking|overtime|show_up_fee`, amount_paise, status: `held|released|paid`, due_by, payout_id null)
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
| Terms click-wrap | Consent pages can't complete without acceptance (sitter: also the sitter consent tick); a sitter can't be approved until she's accepted; acceptance stores version, time, IP and user agent; parent can't book or buy and sitter can't take bookings until the latest version is accepted; parents see parent terms and sitters see the Sitter Terms of Use |
| Documents | Non-admins can't get a signed view URL; every admin view logged; birth certificate deleted after child verification |
| Sitter onboarding | Profile not searchable until every step passes and an admin has set her level |
| Search and filters | Only active, verified, unblocked sitters returned: every level by default (decided 2026-11-09; the parent's page filters by day, language and first aid, and sorts), or one plan's level when asked; distance sort; each filter works; parent never sees sitter pay |
| Sign-up flow | First sign-in asks only the role, then lands in the area; parent can't book until the profile is finished; booking stays unconfirmed until every child on it is verified; sitter not shown to parents until her profile is finished and approved |
| Plans and pricing | Price per plan and children (Pause one child only; Unwind +₹150 per extra child; Recharge flat); whole-hour bookings only (no half-hours); booking `pending_payment` until an admin confirms; rejected or unpaid-by-deadline payment frees the booking |
| Payments | Rows are append-only; amount owed = sum of rows; refunds and cancellation charges per 6.5; parents who owe money can't book |
| Bookings | Sitter's level must match the plan; plan's latest end time (overtime included); bath time only on Unwind/Recharge; two parents can hold `pending_payment` bookings for the same slot, only the first confirmed payment wins it and the other is auto-cancelled; blocked sitter can't be booked |
| Cancellations | Each row of the 6.5 table, including exact 3-hour and 8-hour boundaries |
| Strikes | Ladder 24h / 3d / 1w / 2w / removal; only last-6-month strikes count |
| Check-in/out codes | Codes visible only to the booking's parent and only on the booking day; check-out code only after check-in; codes don't work for other bookings or twice; wrong codes rejected and locked after 5 attempts; locations stored; overdue check-out alert after end + 30 min; admin manual close audit logged; early check-out doesn't refund |
| Overtime | Worked out at check-out; rounded up to the full hour; charged at the plan price, or the next tier's price for hours past the plan's latest end; sitter paid her level pay for the same hours; payment due within 2 hours; unpaid overtime blocks new bookings |
| Incidents | Email sent to every admin address (mocked); payout held while open |
| Sitter pay | Level pay × hours worked, whatever the number of children; hours worked = check-in to booked end; late check-in paid from check-in; overtime hours rounded up like the parent's |
| Payouts | Earnings released only after checkout + overtime worked out + no open incident; due within 12 hours; alerts at 3 hours left and when overdue; show-up fee ₹100 per booked hour; bank or UPI; mark-paid records reference |
| Reviews | Only after a completed booking, once per author per booking; average updates; flag when last-10 average < 3.5 |
| Child age and home info | Child under 18 months can't be booked; camera declaration required; outing needs parent approval |
| New cancellation rows | 15-minute late rule; 20-minute parent-not-home wait; under-18-months: parent charged 1 hour, rest refunded, sitter paid for that hour, no strike; unsafe early exit paid for time worked with no strike after admin confirms; doctor's note strike removal |
| Complaints | SLA timers; escalation; original decider can't handle the appeal; late complaints flagged |
| Sitter terms | Wording matches `sitter-terms-v1.1.md`; placeholders filled from config; production refuses to serve it with an empty placeholder |
| Sitter onboarding extras | Under-18 rejected; health disclosure admin-only and access logged |
| Chat | Only between a parent and sitter who have a booking; admin read is audit logged |
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
