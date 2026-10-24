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
- Prevent duplicate application records or return a predictable conflict response.
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
