# Pacify

Pacify (Pacifyco LLP) is a babysitter marketplace for parents in Bengaluru. Parents browse vetted
sitter profiles, meet a sitter in a free introduction call, then book care paid from pre-bought hour
packs.

Build rules, stack and business rules: [CLAUDE.md](CLAUDE.md). Design system: [design.md](design.md).
Where the build is up to: [progress.md](progress.md).

## Repository layout

```
/web    React + TypeScript + Vite app (parent, sitter and admin areas)
/api    FastAPI app (Python 3.14)
  /app       routers, services, models, schemas
  /tests     pytest tests
.env.example   every environment variable name, no values
```

## Prerequisites

- **Node 24** (see `.nvmrc`)
- **Python 3.14**: the same version is used in CI and on Render
- **Git**
- **Docker Desktop**: runs the local Postgres database

## Local setup

### 1. Environment variables

Copy the example file at the repo root and fill in what you need:

```
cp .env.example .env
```

Both apps read this one `.env`. Never commit it.

For local development you can leave `DATABASE_URL` blank: with `ENVIRONMENT` blank or `local`, the API
uses the Docker database (`postgresql+psycopg://pacifyco:pacifyco@localhost:5432/pacifyco`).

### 2. Database

Start Postgres (from the repo root, with Docker Desktop running):

```
npm run db:start
```

This creates two databases: `pacifyco` for local development and `pacifyco_test` for the API tests.
The tests always use `pacifyco_test` (or `TEST_DATABASE_URL` if set), never your dev data.

| Command | What it does |
| --- | --- |
| `npm run db:start` | Start Postgres |
| `npm run db:stop` | Stop Postgres (data is kept) |
| `npm run db:reset` | Delete all local data and start fresh |

### 3. API

Windows (PowerShell):

```
cd api
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

macOS / Linux:

```
cd api
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The API runs at http://localhost:8000 (interactive docs at http://localhost:8000/docs).

Apply database migrations (`npm run dev` does this for you):

```
alembic upgrade head
```

After changing a model in `app/models`, generate a migration, then read and fix it before committing.
New tables must get Row Level Security; copy `lock_down_tables` from the first migration (a test fails
if any table is missing it).

```
alembic revision --autogenerate -m "short description"
```

Run the tests (the database must be running):

```
pytest
```

Lint and format (CI fails if either finds anything):

```
ruff check . --fix
ruff format .
```

### 4. Web

```
cd web
npm install
npm run dev
```

The app runs at http://localhost:5173.

| Command | What it does |
| --- | --- |
| `npm run dev` | Start the dev server |
| `npm test` | Run the tests (Vitest) |
| `npm run lint` | Lint with ESLint |
| `npm run typecheck` | Type-check with TypeScript |
| `npm run build` | Type-check and build to `web/dist` |

### 5. Run everything with one command

Once steps 1–4 are done, from the repo root:

```
npm run dev
```

This starts Postgres, applies migrations, then starts the API (http://localhost:8000) and the web app (http://localhost:5173), with
their output in one terminal. Ctrl+C stops the API and web app; the database keeps running.

## Branches

Work on feature branches off `develop`. `develop` deploys to staging, `main` to production. Production
releases are a PR from `develop` to `main`.

## Staging deploy

Staging runs from `develop`: the API on Render (service `pacifyco`, `https://pacifyco.onrender.com`), the web app on Cloudflare Pages
(`pacifyco-web-staging`), the database on Supabase (`pacifyco-staging`, Mumbai). Values marked
**secret** go only into the dashboard named; never into the repo, chat or tickets.

### How a merge to `develop` deploys

1. CI runs lint, typecheck and tests.
2. If they pass, the **Migrate staging database** job runs `alembic upgrade head` as the database owner.
3. Render deploys the API once all checks pass ("After CI checks pass"). Cloudflare Pages builds the web
   app on every push to `develop`.

### Database roles

| Role | Used by | Can |
| --- | --- | --- |
| `postgres` | Migrations only (`MIGRATION_DATABASE_URL`) | Everything, including changing tables |
| `pacifyco_api` | The API (`DATABASE_URL`) | Read and write rows (bypasses RLS); can't change tables; audit log is insert-only |

The `pacifyco_api` role is created by a migration without a password. Give it one once per database,
in Supabase → SQL Editor (use a long random password of letters and digits only, so it needs no
escaping in a URL):

```sql
ALTER ROLE pacifyco_api WITH LOGIN PASSWORD 'the-password';
```

Connect through Supabase's **session pooler** (Supabase → Connect → Session pooler; port 5432). Render
can't reach the direct database address, which is IPv6-only. Add `?sslmode=require` to both URLs:

```
postgresql://postgres.<project-ref>:<postgres-password>@<pooler-host>:5432/postgres?sslmode=require
postgresql://pacifyco_api.<project-ref>:<api-password>@<pooler-host>:5432/postgres?sslmode=require
```

### GitHub (environment `staging`, limited to `develop`)

| Secret | Value |
| --- | --- |
| `MIGRATION_DATABASE_URL` | **secret**: the `postgres` session-pooler URL |

### Render web service `pacifyco-api-staging`

| Setting | Value |
| --- | --- |
| Repository, branch | `Pacifyco/pacifyco-app`, `develop` |
| Region | Singapore (closest to Mumbai) |
| Root directory | `api` |
| Runtime | Python |
| Build command | `pip install .` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"` |
| Health check path | `/health` |
| Auto-deploy | After CI checks pass |
| Instance type | Free |

| Environment variable | Value |
| --- | --- |
| `PYTHON_VERSION` | `3.14.0` |
| `ENVIRONMENT` | `staging` |
| `DATABASE_URL` | **secret**: the `pacifyco_api` session-pooler URL |
| `CORS_ORIGINS` | `https://pacifyco-web-staging.pages.dev` |
| `PUBLIC_WEB_URL` | `https://pacifyco-web-staging.pages.dev` |
| `SENTRY_DSN` | Sentry → `pacifyco-api` → Client Keys (DSN) |

### Cloudflare Pages project `pacifyco-web-staging`

| Setting | Value |
| --- | --- |
| Repository | `Pacifyco/pacifyco-app` |
| Production branch | `develop` |
| Framework preset | None |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Root directory | `web` |
| Preview deployments | None (Settings → Build → Branch control) |

| Environment variable | Value |
| --- | --- |
| `NODE_VERSION` | `24` |
| `VITE_ENVIRONMENT` | `staging` |
| `VITE_API_URL` | `https://pacifyco.onrender.com` (the Render service URL) |
| `VITE_SENTRY_DSN` | Sentry → `pacifyco-web` → Client Keys (DSN) |

`VITE_*` values are built into the JavaScript that browsers download, so they must never be secrets.

### Checking staging

- `GET /health`: the API is running (Render's health check; never touches the database). `commit` is the
  first 7 characters of the deployed commit, so after a merge you can see whether Render deployed it.
- `GET /health/db`: the API can sign in to its database. `"api_role": true` means it signed in as
  `pacifyco_api`, as it should when deployed; `false` means `DATABASE_URL` uses another role. A 503 means it
  can't connect (details go to Sentry).

## Production

Production runs from `main` and is set up exactly like staging, with its own database, services and
keys. A release is a PR from `develop` to `main`; when it merges, CI tests it, the **Migrate production
database** job migrates `pacifyco-prod`, then Render and Cloudflare deploy.

Differences from the staging tables above:

| Where | Setting | Production value |
| --- | --- | --- |
| Supabase | Project | `pacifyco-prod` (Mumbai), Data API off, automatic RLS on |
| Supabase | `pacifyco_api` password | Its own password, different from staging's |
| GitHub | Environment | `production` (only `main` can use it), secret `MIGRATION_DATABASE_URL` |
| Render | Service name, branch | `pacifyco-api`, `main` |
| Render | `ENVIRONMENT` | `production` |
| Render | `DATABASE_URL` | **secret**: `pacifyco-prod`'s `pacifyco_api` session-pooler URL |
| Render | `CORS_ORIGINS`, `PUBLIC_WEB_URL` | `https://pacifyco-web.pages.dev` (later `https://www.pacifyco.in`) |
| Render | `SENTRY_DSN` | Same `pacifyco-api` DSN (Sentry tells environments apart) |
| Cloudflare | Project name, production branch | `pacifyco-web`, `main` |
| Cloudflare | `VITE_ENVIRONMENT` | `production` |
| Cloudflare | `VITE_API_URL` | The production Render URL |
| Cloudflare | `VITE_SENTRY_DSN` | Same `pacifyco-web` DSN |

Never seed production with test data (CLAUDE.md section 4). Until launch, production stays on the free
plans and isn't announced; at launch it moves to Supabase Pro and Render Starter.

## Scheduled jobs

`.github/workflows/jobs.yml` calls the API's `POST /internal/jobs/<run>` endpoints with
`Authorization: Bearer <JOBS_SECRET>`. Without the right secret they answer 401, and with no
`JOBS_SECRET` configured nobody can run them. Each run is a list of idempotent tasks in
`api/app/services/jobs.py`.

| Run | When (IST) | Targets | Tasks |
| --- | --- | --- | --- |
| `daily` | 2:00 am | staging and production | keep the database active (more in phases 6–7) |
| `frequent` | every 30 minutes, 6:00 am to midnight | production only until launch | none yet (phases 8–9) |

Run one by hand: GitHub → Actions → Scheduled jobs → Run workflow.

Setup, once per environment (`staging`, `production`), with a new random secret each (40+ letters and
digits):

| Where | What |
| --- | --- |
| Render service (`pacifyco` / `pacifyco-api`) | Environment variable `JOBS_SECRET` (**secret**) |
| GitHub environment `jobs-staging` / `jobs-production` | Secret `JOBS_SECRET`, the same value. Variable `API_URL` is already set. |

The `jobs-*` environments hold only the jobs secret and the API address, never database passwords, and
allow `develop` because GitHub runs schedules from the default branch.

## Sign-in

People sign in with an emailed code or Google, through Supabase Auth. The web app gets a Supabase
access token and sends it to the API, which checks it against the project's public signing keys
(`api/app/auth.py`). Supabase holds no Pacify data: profiles and roles live in our tables.

Settings per Supabase project (staging and production each have their own):

| Where | Setting |
| --- | --- |
| Project Settings → JWT Keys | Current key is asymmetric (ECC P-256 or RSA), not the legacy shared secret |
| Authentication → Emails → SMTP Settings | Custom SMTP: Resend (`smtp.resend.com`, port 465, user `resend`, password = that environment's Resend API key) |
| Authentication → Emails → Templates | "Magic link" and "Confirm signup" show the code (`{{ .Token }}`), not a link |
| Authentication → Sign In / Providers → Email | On; email OTP expiry 600 s; OTP length 6 |
| Authentication → Sign In / Providers → Google | On, with that environment's Google OAuth client ID and secret |
| Authentication → URL Configuration | Site URL = the web URL; Redirect URLs = `<web URL>/auth/callback` (staging also `http://localhost:5173/auth/callback`) |

Environment variables (none are secret): Render `SUPABASE_URL` = `https://<ref>.supabase.co`;
Cloudflare Pages `VITE_SUPABASE_URL` (same) and `VITE_SUPABASE_ANON_KEY` = the project's publishable
key (Project Settings → API Keys, `sb_publishable_...`). Cloudflare needs a new deployment after a
variable changes. Without these, the API refuses every token and the web app says sign-in isn't set up.

### Creating an admin

Admins never sign up through the app (CLAUDE.md 6.13). The person signs in once on that environment's
web app (with the email code or Google), closes the "How will you use Pacify?" page without choosing,
and then Reuben runs, from `api/` with the virtual environment active:

```
MIGRATION_DATABASE_URL='<that environment's session pooler URL, postgres user>' \
  python -m app.cli create-admin --email someone@example.com --name "Full Name"
```

Type the URL into your own terminal (never into chat or a file in the repo). The command looks the
person up in Supabase's sign-in accounts and gives them an active admin profile. It refuses anyone who
already chose parent or sitter. Locally there's no Supabase, so pass `--user-id <uuid>` instead.

### Removing a test account

Deleting a user under Supabase **Authentication → Users** removes only their sign-in account. Their
Pacify profile stays and keeps the email, so signing up again with that email then fails with "This
email already has a Pacify account". Remove the profile first, the same way as creating an admin
(owner URL in your own terminal, from `api/`):

```
python -m app.cli delete-empty-profile --email someone@example.com        # checks only
python -m app.cli delete-empty-profile --email someone@example.com --yes  # deletes
```

It only deletes accounts that hold nothing yet (no children, no sitter application details, no audit
history), so real records are never removed this way. Then delete the user in Supabase if you want the
sign-in account gone too.

## Legal pages

`/terms/sitter`, `/terms/parent` and `/privacy` are public. The texts live in `web/src/content/`. The
Sitter Terms of Use v1.1 is final and a test fails if its wording changes; its blanks are filled from
these Cloudflare Pages variables (public information, set on each project, then redeploy):

| Variable | Fills |
| --- | --- |
| `VITE_PACIFY_LLPIN` | LLPIN |
| `VITE_PACIFY_REGISTERED_ADDRESS` | registered office (both places) |
| `VITE_GRIEVANCE_OFFICER_NAME`, `_EMAIL`, `_PHONE` | Grievance Officer (section 6.3) |
| `VITE_EMERGENCY_LINE` | emergency line during bookings |
| `VITE_SITTER_TERMS_DATE` | "Last updated" date, as `yyyy-mm-dd` |

Outside production a blank value shows as a TEST marker. Production shows "The Sitter Terms aren't
available yet" until every one is set. The privacy policy link fills itself.
