# ai-applier — Decision Log

Record decisions that affect product behavior, architecture, security, or ongoing development. Add new entries at the top. Distinguish a decided choice from a proposal.

## D-001 — Human approval before external submission

- **Status:** Accepted
- **Date:** 2026-10-24
- **Decision:** The product must not submit applications to employers without explicit user approval for that submission.
- **Reason:** Users must control what is sent in their name and be able to review generated materials.
- **Implications:** Any future automation needs a visible review/confirmation step, truthful outcome reporting, and tests that prevent silent submission.

## D-002 — Clerk for authentication

- **Status:** Existing implementation; production readiness still to verify
- **Date:** 2026-10-24
- **Decision:** The current frontend/backend integration uses Clerk.
- **Evidence:** Clerk routes/components and backend authentication code exist in the repository.
- **Follow-up:** Verify token validation, user ownership, production keys, and unauthorized-access behavior.

## D-003 — Next.js frontend and FastAPI backend

- **Status:** Existing implementation
- **Date:** 2026-10-24
- **Decision:** Keep the current Next.js App Router frontend and FastAPI backend for the MVP unless a concrete limitation justifies a change.
- **Reason:** These components are already integrated and the dashboard workflow is working.
- **Follow-up:** Avoid unnecessary framework migrations during core feature development.

## D-004 — Backend is the persistence source of truth

- **Status:** Accepted; core workflow manually verified
- **Date:** 2026-10-24
- **Decision:** Job/application changes must be persisted by the backend. Frontend state provides immediate feedback but must reconcile with API responses.
- **Evidence:** Saving a job, marking it applied, and refreshing was reported working.
- **Follow-up:** Add automated integration tests and verify error/duplicate behavior.

## D-005 — Documentation-led implementation

- **Status:** Accepted
- **Date:** 2026-10-24
- **Decision:** Use `PRD.md` for requirements, `ROADMAP.md` for progress, `ARCHITECTURE.md` for system boundaries, and `API.md` for API contracts.
- **Rule:** Update the relevant documents when a change materially changes behavior or scope.

## Pending decisions

- Initial job sources and access strategy.
- Candidate profile fields and resume formats.
- AI provider/model and budget/rate limits.
- Application status transition policy.
- Production hosting and database.
- Data retention, deletion, and backup requirements.
