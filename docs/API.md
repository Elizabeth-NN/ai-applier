# ai-applier — API Reference

- **Status:** Initial route inventory; not a complete OpenAPI contract.
- Check the FastAPI OpenAPI document and the Pydantic schemas before changing request/response shapes.

## Base URL

Local development commonly uses `http://127.0.0.1:8000`. The frontend reads its backend URL from `NEXT_PUBLIC_API_URL`. Production URLs must be configured separately.

## Known routes

| Method | Path | Purpose | Authentication notes |
|---|---|---|---|
| GET | `/` | Backend root/status response | Verify implementation |
| GET | `/api/health` | Backend health check | Verify implementation |
| GET | `/api/health/db` | Database health check | Verify implementation |
| GET | `/api/me` | Return current authenticated user information | Authentication required |
| POST | `/api/jobs` | Create a job record | Verify current route dependency |
| GET | `/api/jobs` | List jobs; accepts a `limit` query parameter | Current listing is not user-scoped |
| GET | `/api/jobs/{job_id}` | Retrieve a job by ID | Verify current route dependency |
| POST | `/api/applications` | Create an application for a job | Authentication required; ownership must be server-derived |
| GET | `/api/applications` | List the current user's applications; accepts `limit` | Authentication required and user-scoped |
| PATCH | `/api/applications/{application_id}` | Update application status | Authentication and ownership required |

This inventory comes from route declarations and current integration context. Confirm exact status codes, request bodies, response schemas, pagination semantics, and error behavior in the code or `/docs`.

## Current dashboard integration

The dashboard calls:
- `GET /api/jobs?limit=100`
- `GET /api/applications?limit=100`
- `POST /api/applications` with a job ID and optional notes
- `PATCH /api/applications/{application_id}` with the next status

The dashboard sends a Clerk bearer token. Job listing may currently be publicly accessible; sending a token does not make a public endpoint user-scoped.

## Application status values

The frontend currently recognizes:
- `saved`
- `applied`
- `interview`
- `rejected`
- `offer`

The user interface labels these as Saved, Applied, Interview, Rejected, and Offer. Keep frontend types, backend schema validation, and database constraints aligned. Decide explicitly whether status transitions are unrestricted or governed by a transition policy.

## API conventions to adopt

- Validate request data with Pydantic schemas.
- Return appropriate HTTP status codes and stable error formats.
- Require authentication for user-specific operations.
- Derive ownership from the authenticated identity, never an untrusted request field.
- Return `404` or another deliberately chosen safe response for records the user cannot access.
- Add pagination before result volumes grow.
- Enforce one application per user/job pair with the database constraint `uq_applications_user_job`.
- `POST /api/applications` returns `201 Created` for a new application. If the authenticated user has already saved that job, it returns `200 OK` with the existing record and preserves its notes and status.
- Different users may save the same job independently. The `user_id` must come from the authenticated identity, not the request body.
- Keep timestamps consistently timezone-aware.
- Avoid returning internal stack traces or secrets.
- Test both successful requests and unauthorized/invalid requests.

## Contract verification checklist

- [ ] Inspect `backend/app/api/jobs.py`.
- [ ] Inspect `backend/app/api/applications.py`.
- [ ] Inspect `backend/app/schemas/job.py` and `backend/app/schemas/application.py`.
- [ ] Inspect `backend/app/core/auth.py`.
- [ ] Inspect `backend/app/models/`.
- [ ] Review `/docs` and `/openapi.json` in local development.
- [ ] Add tests for authentication, ownership, validation, missing records, duplicates, and status updates.

## Application execution routes

The application-execution API supports preparation and a human-controlled
execution lifecycle. These routes require authentication and enforce ownership.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/application-executions/prepare` | Prepare an application execution; accepts an `Idempotency-Key` header |
| GET | `/api/application-executions` | List the authenticated user's executions |
| POST | `/api/application-executions/{execution_id}/review` | Record candidate review of a prepared execution |
| POST | `/api/application-executions/{execution_id}/approve` | Approve a reviewed execution |
| POST | `/api/application-executions/{execution_id}/start` | Record the start of a genuine submission attempt |
| POST | `/api/application-executions/{execution_id}/complete` | Record a confirmed submission outcome |
| POST | `/api/application-executions/{execution_id}/fail` | Record a failed submission attempt |
| POST | `/api/application-executions/{execution_id}/needs-attention` | Flag an uncertain outcome for human follow-up |

Preparation stores a snapshot of the application data. Review and approval
do not submit an application. Starting an execution records an attempt but
does not itself contact an employer or submit an external form.

Completion records a reported or trusted confirmation; it does not
independently verify the employer's system. An uncertain result must not be
reported as submitted.

The execution lifecycle is separate from application tracking status.
Only a confirmed completion may move a linked application from `saved` to
`applied`; later tracking statuses must be preserved.

## Planned Chrome extension handoff routes

**Status: Planned — not implemented.**

The following routes are architectural proposals, not available API endpoints:

| Method | Proposed path | Purpose |
|---|---|---|
| POST | `/api/application-executions/{execution_id}/extension-handoff` | Issue a short-lived, single-use credential for an owned, approved execution |
| POST | `/api/extension-handoffs/redeem` | Redeem the opaque credential and retrieve the permitted application snapshot |

The issuance endpoint will require the authenticated candidate's identity
and verify execution ownership and approval. The redemption endpoint is
intended to use the opaque handoff credential rather than a Clerk session
token.

The backend should store only a hash of the credential and atomically enforce
expiry and single-use redemption. Replacing a handoff must invalidate the
previous unredeemed credential. Exact request and response schemas, status
codes, rate limits, and error behavior must be documented when these routes
are implemented.

The extension must not receive a reusable Clerk session token or backend
secret. Handoff credentials and sensitive application snapshots must not be
persisted in extension storage.
