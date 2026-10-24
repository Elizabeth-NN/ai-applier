# ai-applier — Architecture

- **Status:** Current-state overview based on repository inventory and manual workflow reports.
- Verify implementation details in source before making structural changes.

## 1. System overview

```text
Browser
  |
  v
Next.js frontend (frontend/)
  |-- App Router pages
  |-- Clerk authentication UI/session
  |-- Dashboard and application-tracking UI
  |
  | HTTPS/JSON requests; authenticated requests carry a Clerk bearer token
  v
FastAPI backend (backend/app/)
  |-- API routes
  |-- Authentication dependency
  |-- Pydantic schemas
  |-- SQLAlchemy models/session
  |
  v
Configured relational database
  |-- Jobs
  |-- Applications
  |-- Alembic-managed schema migrations
```

This diagram describes the known shape of the application, not a guarantee that every production environment is configured.

## 2. Frontend

Observed files:
- `frontend/app/page.tsx` — landing page.
- `frontend/app/dashboard/page.tsx` — dashboard and current job/application workflow.
- `frontend/app/sign-in/[[...sign-in]]/page.tsx` — sign-in route.
- `frontend/app/sign-up/[[...sign-up]]/page.tsx` — sign-up route.
- `frontend/components/ApplicationTracker.tsx` — application-tracking component.
- `frontend/components/BackendAuthCheck.tsx` — backend authentication diagnostic component.
- `frontend/components/Navbar.tsx` — navigation component.
- `frontend/proxy.ts` — request proxy/middleware-related configuration; inspect before changing auth routing.
- `frontend/app/globals.css` — global styling.

The dashboard currently calls the backend for jobs and applications, then joins those records in the UI. The UI should not treat client-side state as the source of truth for persisted data.

## 3. Backend

Observed files:
- `backend/app/main.py` — FastAPI application, health routes, current-user route, and application setup.
- `backend/app/api/jobs.py` — job endpoints.
- `backend/app/api/applications.py` — application endpoints.
- `backend/app/core/auth.py` — authentication logic.
- `backend/app/core/config.py` — configuration.
- `backend/app/db/session.py` and `backend/app/db/dependencies.py` — database setup and dependencies.
- `backend/app/models/` — SQLAlchemy models.
- `backend/app/schemas/` — API schemas.
- `backend/migrations/` — Alembic migrations.

The backend, not the browser, must enforce authorization and validate mutations.

## 4. Authentication and authorization

Clerk is the configured authentication provider. Frontend requests use a session token where required. The backend exposes `/api/me` and has authentication code in `backend/app/core/auth.py`.

Rules:
- Never trust a user ID supplied only by the browser for ownership.
- Derive the acting user from a verified token on the backend.
- Check ownership for every read or mutation of user-owned resources.
- Do not expose secret keys in frontend variables. Only intentionally public values may use the `NEXT_PUBLIC_` prefix.
- Treat frontend hiding/disabling as a UX feature, not a security boundary.
- Verify auth behavior with tests, including attempts to access another user's record.

## 5. Data model

Observed model modules:
- `backend/app/models/job.py`
- `backend/app/models/application.py`

Observed migration history includes creation of jobs/applications tables and addition of application `user_id`.

The dashboard's current application data includes fields such as application ID, job ID, status, notes, applied timestamp, creation timestamp, and update timestamp. Confirm the canonical definitions in models and schemas before extending them.

Potential future entities such as candidate profiles, resume documents, generated documents, matching results, and ingestion runs are product proposals—not confirmed existing models.

## 6. API communication

- Use JSON for structured requests and responses.
- Use bearer authentication for protected endpoints.
- Handle non-2xx responses without assuming a successful mutation.
- Return clear, stable error messages and appropriate HTTP status codes.
- Avoid duplicate fetches and prevent stale requests from overwriting newer state.
- Document canonical request/response contracts in `API.md` and the source schemas.

## 7. Database and migrations

Alembic migration files exist under `backend/migrations/versions/`.

Rules:
- Schema changes require a migration.
- Do not manually alter a production schema without a migration plan.
- Review generated migrations before applying them.
- Test migrations against a disposable/test database.
- Document backup and restore procedures before production use.

## 8. Proposed future boundaries

As the product grows, keep responsibilities separate:
- Job ingestion/source adapters.
- Job normalization and deduplication.
- Candidate profile and document storage.
- Matching and explanation service.
- AI document-generation service.
- Application workflow and any user-approved automation.
- Observability and operational tooling.

Do not introduce these abstractions prematurely; add them when a concrete feature needs them.

## 9. Source of truth

When documentation and code disagree:
1. Inspect the code and tests.
2. Determine intended behavior from `PRD.md` and `DECISIONS.md`.
3. Fix the discrepancy deliberately.
4. Update documentation and tests in the same change.
