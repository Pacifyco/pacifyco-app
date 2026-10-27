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

## Local setup

### 1. Environment variables

Copy the example file at the repo root and fill in what you need:

```
cp .env.example .env
```

Both apps read this one `.env`. Never commit it.

### 2. API

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

Run the tests:

```
pytest
```

### 3. Web

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
| `npm run typecheck` | Type-check with TypeScript |
| `npm run build` | Type-check and build to `web/dist` |

## Branches

Work on feature branches off `develop`. `develop` deploys to staging, `main` to production. Production
releases are a PR from `develop` to `main`.
