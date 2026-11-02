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

## Resume upload and matching

Resume endpoints require authentication. Resume records and files are scoped
to the authenticated user.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/resumes` | Upload a PDF or DOCX resume (maximum 5 MB) |
| GET | `/api/resumes` | List the authenticated user's resumes |
| GET | `/api/resumes/{resume_id}/download` | Download an owned resume |
| DELETE | `/api/resumes/{resume_id}` | Delete an owned resume and its stored file |
| GET | `/api/jobs/matches` | Rank stored jobs against an owned resume |

### Match request

`GET /api/jobs/matches?resume_id=1&skip=0&limit=20`

| Parameter | Required | Default | Constraints |
|---|---|---|---|
| `resume_id` | Yes | — | Integer, at least 1; must belong to the authenticated user |
| `skip` | No | `0` | Integer, at least 0 |
| `limit` | No | `20` | Integer, 1–100 |

The endpoint extracts text from the selected PDF or DOCX resume, prepares
matching features, parses recognized resume sections, and scores stored jobs.
It ranks the complete result set before applying pagination.

### Match response

The response contains:

- `resume_id` and `resume_filename`: the selected resume.
- `items`: the current page of job records with matching information.
- `total`: number of scored jobs before pagination.
- `skip` and `limit`: pagination values.

Each item extends the normal job representation with:

| Field | Meaning |
|---|---|
| `match_score` | Bounded text-relevance score from 0 to 100 |
| `matched_terms` | Informative terms found in both job text and resume text |
| `terms_not_found_in_resume` | Informative job terms not located in extracted resume text |
| `required_terms_found` | Explicit required terms found in the resume |
| `required_terms_not_found` | Explicit required terms not located in the resume |
| `preferred_terms_found` | Preferred terms found in the resume |
| `preferred_terms_not_found` | Preferred terms not located in the resume |
| `term_evidence` | Required/preferred term evidence grouped by recognized resume section |
| `match_reasons` | Human-readable explanations of the text match |

`term_evidence` maps requirement terms to section names such as `skills`,
`experience`, `projects`, `summary`, `education`, and `certifications`.
An empty section list means the parser did not locate that term in its
recognized sections; it does not establish that the candidate lacks the skill.

### Matching interpretation and limitations

The current matcher is deterministic and text-based. Its component weights
are 45% job-title overlap, 30% job-description overlap, and 25% explicit
requirement overlap, with confidence adjustments for limited evidence.
Preferred terms are reported separately and do not add a separate score
component.

Text normalization removes URLs, email addresses, and unambiguous
multi-word employer-name noise. Corpus-wide term weighting gives more
distinctive terms greater influence than generic terms.

The score measures textual overlap, not hiring probability, verified
proficiency, qualification equivalence, or likelihood of an interview.
Missing textual evidence does not prove a candidate lacks a skill.
Resume matching does not determine whether an employer accepts applicants
from Kenya; geographic eligibility and listing status are separate checks.

The parser recognizes configured resume headings and groups their content
into sections. It is a lightweight section parser, not a complete extraction
of employers, job titles, dates, or individual skill records. Results can
depend on document formatting and heading recognition.

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
