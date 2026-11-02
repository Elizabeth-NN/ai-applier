# ai-applier — Implementation Roadmap

- **Status:** Proposed; update after each audit or completed milestone.
- **Rule:** Do not mark a feature complete merely because its page exists.

## Status definitions

- `[x]` Implemented and verified against its acceptance criteria.
- `[~]` Partially implemented or only manually verified.
- `[ ]` Not yet verified or not implemented.
- `[!]` Blocked or needs a decision.

## Phase 0 — Baseline and project hygiene

- [x] Next.js frontend and FastAPI backend exist.
- [x] Clerk authentication integration exists.
- [x] SQLAlchemy models and Alembic migrations exist.
- [x] Dashboard loads jobs and the current user's applications.
- [x] Save-job and status-update workflow manually verified, including refresh persistence.
- [x] Frontend TypeScript, ESLint, and production build passed on 2026-10-24.
- [ ] Identify and run project-owned backend tests; exclude virtual environments from discovery.
- [ ] Audit every navigation item and dashboard action.
- [ ] Review Git ignore rules, secret handling, and repository hygiene.
- [ ] Add and maintain product/technical documentation.

## Phase 1 — Core data and security

- [ ] Verify ownership checks for every user-owned resource and mutation.
- [ ] Verify unauthenticated, expired-token, and cross-user access behavior.
- [ ] Decide and implement duplicate-application handling.
- [ ] Add pagination and predictable API validation/error responses where needed.
- [ ] Review database constraints, migrations, indexes, and transaction behavior.
- [ ] Add backend tests for jobs, applications, authentication, and ownership.
- [ ] Confirm all dashboard statistics use real and clearly defined data.

**Exit gate:** core job/application operations pass automated tests, including negative authorization tests.

## Phase 2 — Candidate profile and documents

- [ ] Audit existing code for profile and resume functionality before implementation.
- [ ] Define profile schema and validation.
- [ ] Implement profile create/read/update operations and UI.
- [x] Support PDF and DOCX resume uploads with a 5 MB limit.
- [x] Store resume files privately and scope listing, download, and deletion to the owner.
- [x] Add resume file validation and ownership tests.
- [x] Extract resume text for matching and document-generation workflows.

**Exit gate:** a user can securely upload, access, and delete their own resume documents. Profile management remains outstanding.

## Phase 3 — Job ingestion and discovery

- [ ] Choose initial legitimate job sources and confirm access requirements.
- [ ] Define a normalized job schema and source attribution.
- [ ] Implement ingestion, deduplication, and failure reporting.
- [ ] Add search, filters, and pagination.
- [ ] Preserve source links and avoid presenting expired or uncertain jobs as verified active jobs.
- [ ] Add ingestion tests and a repeatable update process.

**Exit gate:** the catalog can be populated and refreshed reliably, with duplicate and source behavior tested.

## Phase 4 — Matching and AI assistance

- [ ] Select the provider/model and define cost and rate limits.
- [x] Define and implement an explainable resume-to-job matching contract.
- [x] Rank stored jobs against an authenticated user's uploaded resume.
- [x] Explain matched terms, missing textual evidence, and required/preferred requirements.
- [x] Show requirement evidence by recognized resume section.
- [x] Keep resume relevance separate from geographic eligibility and listing status.
- [x] Add deterministic regression tests for matching, requirement classification, and text-noise reduction.
- [ ] Improve structured resume extraction beyond heading-based section grouping.
- [ ] Evaluate AI-assisted matching separately from the deterministic baseline.
- [ ] Generate editable, job-specific resume/cover-letter drafts.
- [ ] Add timeouts, retries where appropriate, provider error handling, and tests.
- [ ] Clearly distinguish generated suggestions from user-approved content.

**Exit gate:** deterministic matching is explainable and tested. Any future provider-backed outputs must be grounded in supplied data, reviewable, and fail safely when the provider is unavailable.

## Phase 5 — Application workflow

- [ ] Complete application detail and notes workflow.
- [ ] Define status transitions and application history.
- [ ] Provide a clear review/approval step for each application.
- [ ] If browser automation is added, require explicit confirmation before submission.
- [ ] Record what was submitted and the outcome without storing unnecessary sensitive data.
- [ ] Test cancellation, failures, and duplicate actions.

**Exit gate:** a user can manage an application from discovery through tracking, with no silent external submissions.

## Phase 5A — Browser-assisted ATS preparation (planned)

- [ ] Add the database migration for extension handoff credential fields.
- [ ] Implement authenticated handoff issuance for owned, approved executions.
- [ ] Implement atomic, single-use redemption with expiry and replay protection.
- [ ] Test ownership, approval, expiry, invalidation, and concurrent redemption.
- [ ] Create the Chrome Manifest V3 extension structure.
- [ ] Implement Greenhouse detection and supported-field adapters.
- [ ] Populate fields only after an explicit candidate action.
- [ ] Let candidates review and correct populated fields before submission.
- [ ] Keep login, CAPTCHA, human verification, resume uploads, and unsupported fields manual.
- [ ] Never automate the employer Submit action.
- [ ] Verify that form population does not advance the execution lifecycle.
- [ ] Evaluate Lever and Ashby only after the Greenhouse workflow is validated.

**Exit gate:** secure handoff tests pass, supported fields are reviewable, and no application is submitted without direct candidate action.

## Phase 6 — Quality and operational readiness

- [ ] Add automated frontend tests for key interactions.
- [ ] Add backend integration tests and authorization tests.
- [ ] Run the full test suite and production build.
- [ ] Audit accessibility and responsive behavior.
- [ ] Verify environment variables, CORS, HTTPS, database migrations, and secrets.
- [ ] Document logging, backups, restore procedures, and incident troubleshooting.
- [ ] Test the production deployment using a non-destructive smoke-test checklist.

**Exit gate:** the MVP completion gate in `PRD.md` is satisfied.

## Working agreement

1. Inspect before editing.
2. Prefer small, reversible changes.
3. Write acceptance criteria before implementing a feature.
4. Add tests for new behavior and regressions.
5. Run relevant checks after each change.
6. Review `git diff` before committing.
7. Do not deploy until the deployment gate is met.
8. Update this roadmap when work is verified—not merely attempted.
