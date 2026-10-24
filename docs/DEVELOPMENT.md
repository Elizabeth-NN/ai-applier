# ai-applier — Development Guide

## Repository layout

- `frontend/` — Next.js application.
- `backend/` — FastAPI application, models, schemas, database configuration, and migrations.
- `docs/` — product and engineering reference documents.

## Prerequisites

- Python version supported by `backend/requirements.txt` (the current environment uses Python 3.12).
- Node.js version supported by the frontend project.
- npm.
- A configured database.
- Clerk development credentials.
- A configured backend URL in the frontend environment.

Check the actual project configuration before upgrading runtimes or dependencies.

## Environment files

Files observed in the repository:
- `backend/.env`
- `backend/.env.example`
- `frontend/.env.local`

Do not commit real secrets. Keep examples limited to placeholder values. Review `git status` and ignore rules before committing.

Frontend environment variables commonly include:
- `NEXT_PUBLIC_API_URL`
- The public Clerk publishable key expected by the frontend setup.

Backend variables depend on `backend/app/core/config.py` and `backend/.env.example`; inspect those files rather than guessing names.

Never paste real secret values into issues, logs, commits, or chat.

## Start the backend

From the repository root, in a dedicated terminal:

```bash
cd ~/Development/code/personal/ai-applier
source backend/.venv/bin/activate
PYTHONPATH=backend uvicorn app.main:app --app-dir backend --reload
```

If the virtual environment is elsewhere, activate the environment actually used by the project.

Check the routes:
```bash
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1:8000/api/health/db
```

Interactive API documentation is normally available at `http://127.0.0.1:8000/docs` when enabled.

## Start the frontend

In a separate terminal:

```bash
cd ~/Development/code/personal/ai-applier/frontend
npm install
npm run dev
```

Open the local URL printed by Next.js, commonly `http://localhost:3000`.

## Frontend checks

Run before committing frontend changes:

```bash
cd ~/Development/code/personal/ai-applier/frontend
npx tsc --noEmit
npm run lint
npm run build
```

These checks passed on 2026-10-24 for the then-current dashboard commit. Run them again after later changes.

## Backend tests

First discover project-owned tests while excluding the virtual environment:

```bash
cd ~/Development/code/personal/ai-applier
find backend -path 'backend/.venv' -prune -o \
  -type f \( -name 'test_*.py' -o -name '*_test.py' \) -print
```

If tests exist, activate the backend environment and run the repository's intended test command. Do not assume the presence of pytest's installed test files means the project has tests.

## Database migrations

Inspect migration state before applying migrations. Review `backend/alembic.ini`, `backend/migrations/env.py`, and `backend/migrations/README`. Test schema changes against a disposable database first.

Do not reset, drop, or seed a database containing valuable user data as part of routine development.

## Change workflow

1. Read `docs/PRD.md`, `docs/ROADMAP.md`, and relevant architecture/API docs.
2. Inspect current implementation and tests before editing.
3. Define expected behavior and acceptance criteria.
4. Make a focused change.
5. Add or update tests.
6. Run relevant checks.
7. Review `git diff --check`, `git diff`, and `git status`.
8. Update documentation when behavior, API contracts, or decisions change.
9. Commit and push only after reviewing the changes.

## Manual smoke-test workflow

- Sign in.
- Load jobs from the backend.
- Save a job.
- Change its status.
- Refresh and verify persistence.
- Confirm the application belongs to the signed-in user.
- Test a failed API request and an expired/signed-out session.
- Verify another user cannot access the application's record.

The save/status/refresh workflow was manually reported working on 2026-10-24. The negative authorization cases still need explicit verification.
