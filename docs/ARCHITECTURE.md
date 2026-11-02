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

### Resume parsing and job matching

The resume-to-job matching flow is implemented across these components:

- `backend/app/api/resumes.py` — authenticated resume upload, listing,
  download, deletion, and ownership checks.
- `backend/app/services/resume_text.py` — PDF/DOCX text extraction.
- `backend/app/services/structured_resume_parser.py` — deterministic
  section recognition and grouping.
- `backend/app/services/resume_job_matching.py` — text normalization,
  feature preparation, corpus term weighting, scoring, requirement
  classification, and section-level evidence.
- `backend/app/api/jobs.py` — authenticated `GET /api/jobs/matches`
  orchestration and pagination.
- `backend/app/schemas/job.py` — typed match response schemas.

The matching request selects an uploaded resume by `resume_id`. The backend
resolves it using both the resume ID and authenticated user identity, checks
the stored path, extracts its text, and prepares matching features.

The structured parser recognizes common headings for summary, skills,
experience, projects, education, certifications, contact information, and
other sections. Section features are used to explain where requirement terms
appear. This evidence is explanatory and does not change the relevance score.

The matcher compares resume text with stored job titles, descriptions, and
explicit requirements. Its component weights are 45% title overlap, 30%
description overlap, and 25% requirement overlap. Confidence adjustments
account for limited evidence. Preferred requirements are classified and
reported separately.

Job-corpus term weights are prepared independently of the selected resume.
Jobs are scored and ranked before `skip`/`limit` pagination is applied.

This baseline is deterministic; it does not require an AI provider call.
The score represents textual relevance, not hiring probability or verified
candidate proficiency. Geographic eligibility, listing status, and resume
fit remain separate dimensions.

The parser is intentionally lightweight. It groups text under recognized
headings rather than extracting a complete structured employment history.
Unknown headings and unusual document layouts can affect section evidence.

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


## 9. Browser-assisted ATS extension (planned)

The Chrome extension will be a separate backend client. It will assist with
supported employer application forms without taking control of submission.

### Proposed structure

- `extension/manifest.json`: Chrome Manifest V3 configuration.
- `extension/src/background/`: extension coordination and backend handoff.
- `extension/src/content/`: ATS page detection and form interaction.
- `extension/src/adapters/`: ATS-specific detection and field mapping.
- `extension/src/shared/`: shared types, messages, and validation.

Greenhouse is the initial ATS target. Lever and Ashby may follow after
validation.

### Secure handoff

1. The candidate signs in to the dashboard using Clerk.
2. The dashboard requests a handoff for an approved execution.
3. The backend verifies authentication, execution ownership, and approval.
4. The backend issues a random, short-lived, single-use opaque credential.
5. Only the credential hash is stored by the backend.
6. The extension background service worker redeems the credential.
7. The backend atomically consumes it and returns the minimum required
   application snapshot.
8. Sensitive data remains in memory and is not persisted in extension storage.

The initial expiry target is five minutes. Issuing a replacement credential
invalidates any previous unredeemed credential for that execution.

### Security boundaries

- Never expose the Clerk secret key to the extension.
- Do not broaden Clerk authorized parties or backend CORS for arbitrary
  extension origins.
- Never send the handoff credential to content scripts.
- Enforce expiry, single-use redemption, execution scope, and replay protection.
- Never log credentials, resume contents, or full application snapshots.
- Restrict extension host permissions to supported sites and required
  dashboard/backend communication.
- Keep login, CAPTCHA, human verification, and final submission under
  candidate control.

### Execution lifecycle boundary

ATS detection, navigation, and form population do not start a submission.
The existing `start` operation is reserved for a genuine submission attempt.
Record completion only after a confirmed outcome. Flag uncertain outcomes for
human attention rather than blindly retrying.

## 10. Source of truth

When documentation and code disagree:
1. Inspect the code and tests.
2. Determine intended behavior from `PRD.md` and `DECISIONS.md`.
3. Fix the discrepancy deliberately.
4. Update documentation and tests in the same change.
