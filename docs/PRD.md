# ai-applier — Product Requirements Document

- **Document status:** Living draft
- **Baseline date:** 2026-10-24
- **Product:** ai-applier
- **Purpose:** Source of truth for product scope and acceptance criteria

## 1. Product vision

ai-applier helps job seekers organize their search and prepare higher-quality job applications with AI assistance. It should bring job discovery, candidate information, application materials, and application tracking into one workflow.

The product should reduce repetitive work without taking away the user's control over what is submitted to employers.

## 2. Problem statement

A job seeker may need to search across multiple sources, assess whether a role fits their background, tailor application documents, and remember the status of many applications. This work is fragmented and repetitive.

ai-applier aims to make that workflow easier by keeping relevant information together and assisting with research and document preparation.

## 3. Initial target users

The initial user is an individual job seeker applying for entry-level, junior, graduate, and other relevant software roles. The product should be designed so that its workflow can later support other job categories.

Initial product priorities:
- Search and organize relevant job opportunities.
- Maintain an accurate candidate profile.
- Track each application's progress.
- Prepare application materials for the user to review.
- Make recommendations understandable and editable.

## 4. Product principles

1. **Human approval:** Never submit an application to an employer without explicit user approval for that submission.
2. **Truthfulness:** Do not invent qualifications, experience, education, skills, or achievements.
3. **User privacy:** A user's private profile, documents, and applications must not be visible to another user.
4. **Persistence:** Changes confirmed as saved must survive a page refresh and a new session.
5. **Transparency:** Clearly distinguish real results from examples, estimates, AI suggestions, and unavailable data.
6. **Reliability:** Show useful loading, empty, success, and error states.
7. **Incremental delivery:** Build and verify a complete workflow before adding unnecessary complexity.

## 5. Scope

### MVP capabilities

#### A. Authentication and account boundaries
- Users can sign up, sign in, and sign out through the configured authentication provider.
- Protected operations require a valid authenticated identity.
- Every user-owned resource is scoped to its owner on the server.
- Authentication failures are handled clearly in the UI.

#### B. Job catalog and discovery
- Display job listings retrieved from the backend.
- Show available source information and a link to the original listing where provided.
- Support searching and filtering the catalog.
- Handle loading, empty, stale, and failed requests.
- Avoid presenting the entire catalog as AI-matched unless matching has actually been implemented.

#### C. Candidate profile
- Store relevant skills, experience, education, location, work preferences, and target roles.
- Allow the user to review and update their information.
- Use the profile as the source of truth for later matching and document generation.

#### D. Application tracking
- Save a job to a user's application pipeline.
- Track statuses such as Saved, Applied, Interview, Rejected, and Offer.
- Persist status changes in the backend.
- Display the user's own applications and useful summary statistics.
- Prevent accidental duplicate records or handle them predictably.
- Preserve notes and relevant application history.

#### E. Application materials
- Allow the user to provide or upload a resume.
- Support AI-assisted resume tailoring and cover-letter generation.
- Let users review and edit generated content before using it.
- Keep generated content linked to the relevant job where appropriate.
- Never claim a document was saved or generated unless the operation succeeded.

#### F. Explainable resume-to-job matching

**Implemented baseline:** Users can compare stored jobs with an uploaded PDF
or DOCX resume through deterministic text matching.

- Require an authenticated user and a resume owned by that user.
- Compare job title, description, and explicit requirements with extracted
  resume text.
- Show a bounded relevance score, matched terms, missing textual evidence,
  required/preferred requirement evidence, and human-readable match reasons.
- Where possible, show which recognized resume sections contain requirement
  terms.
- Keep resume fit separate from Kenya eligibility and listing status.
- Explain that missing text evidence does not prove the candidate lacks a
  qualification, and that a match score is not a hiring probability.

**Future improvements:** richer candidate profiles, more robust structured
resume extraction, and AI-assisted matching may be considered separately.
They must remain grounded in candidate-provided information and explainable
to the user.

#### G. User-controlled application workflow
- Let the user review the destination, job, and application materials.
- Require explicit confirmation before any external submission.
- Report the outcome accurately; do not equate opening a job page with applying.

### H. Browser-assisted application preparation (planned)

- Provide an optional Chrome extension for supported ATS application forms.
- Start with Greenhouse; consider Lever and Ashby after validation.
- Detect supported application pages and populate supported fields only after
  the candidate explicitly requests assistance.
- Allow the candidate to review and correct every populated field.
- Keep unsupported platforms and unsupported fields available through manual
  completion.
- Keep CAPTCHA, login, human verification, resume uploads, and final submission
  under direct candidate control.
- Never click the employer's Submit button automatically.
- Never mark an application as submitted merely because its form was populated.
- Retrieve approved application data through a short-lived, single-use,
  execution-scoped backend handoff.

### Out of scope for the initial MVP
- Unattended bulk application submission.
- Fabricating or embellishing candidate qualifications.
- Promising interviews, employment, or a particular matching accuracy.
- Complex team, recruiter, or employer-facing functionality unless separately approved.
- Paid integrations before a cost and value assessment.

## 6. Functional requirements and acceptance criteria

| ID | Requirement | Acceptance criteria |
|---|---|---|
| FR-01 | Authentication | Signed-out users cannot access protected user data or mutations. |
| FR-02 | Job catalog | Listings come from the backend; errors and empty results are explained. |
| FR-03 | Save job | A successful save creates one application record for the current user and job. |
| FR-04 | Status updates | A status change is persisted by the backend and remains after refresh. |
| FR-05 | Data isolation | User A cannot read or modify User B's applications by changing IDs or requests. |
| FR-06 | Candidate profile | A user can create, view, and update their own profile. |
| FR-07 | Documents | A user can manage their own resume and generated materials safely. |
| FR-08 | Matching | A recommendation uses available job/profile data and gives a truthful explanation. |
| FR-09 | AI generation | Generated materials are editable and grounded in the user's real qualifications. |
| FR-10 | Human approval | External application submission requires explicit confirmation. |
| FR-11 | Reliability | Main screens provide loading, empty, success, and failure states. |
| FR-12 | Maintainability | Documented checks pass, and new critical behavior has automated tests. |
| FR-13 | ATS detection | The extension identifies supported ATS pages and clearly reports unsupported pages. |
| FR-14 | Secure extension handoff | Only an owned, approved execution can receive a short-lived, single-use extension handoff. |
| FR-15 | Assisted form population | Supported fields are populated only after an explicit candidate action and remain reviewable and editable. |
| FR-16 | Submission integrity | The extension never submits applications automatically or reports submission without a confirmed outcome. |

Requirements FR-01 through FR-05 have some existing implementation according to the current repository inventory and manual dashboard test. Their full security and edge-case acceptance criteria still require verification. FR-06 onward must be audited before being classified as missing or unimplemented.

## 7. Non-functional requirements

- **Security:** Validate inputs, protect secrets, enforce ownership on the backend, and restrict cross-origin access to approved origins.
- **Privacy:** Collect only necessary information and avoid logging sensitive document contents or tokens.
- **Performance:** Paginate larger result sets and avoid unnecessary API requests.
- **Accessibility:** Use semantic controls, visible focus, readable contrast, and accessible error messages.
- **Resilience:** Handle unavailable services, expired sessions, invalid responses, and network failures.
- **Maintainability:** Keep API contracts, environment setup, decisions, and test commands documented.
- **Cost awareness:** Prefer free or low-cost services for the MVP and make AI-provider costs explicit.

## 8. Success measures

Do not invent baseline numbers. Establish measurements after core functionality is stable:
- Percentage of core workflow tests passing.
- Successful job saves and status updates.
- Duplicate application rate.
- API error rate and time to load the dashboard.
- Percentage of generated materials accepted after user review.
- User-reported usefulness of job recommendations.

## 9. MVP completion gate

The MVP is ready for deployment consideration only when:
- Core user flows work end to end.
- Ownership and authentication checks pass.
- Database migrations and backup/recovery expectations are documented.
- No key screen depends on misleading hardcoded demo records.
- AI output is reviewable and cannot silently submit applications.
- Automated checks pass.
- Production environment, CORS, authentication, and database configuration are verified.
- Known limitations and operational procedures are documented.

## 10. Open questions

Resolve these through repository inspection and deliberate product decisions:
- Which job sources will be supported first, and under what access terms?
- Which resume file formats and size limits are required?
- Which AI provider/model should be used, and what are the cost limits?
- What is the final application status lifecycle?
- What retention and deletion controls should users have?
- Which hosting and database services will be used in production?

## 11. Document maintenance

Update this PRD when product scope changes. Keep implemented status in the roadmap, not by silently weakening acceptance criteria. Record consequential decisions in `DECISIONS.md`.
