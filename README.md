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
