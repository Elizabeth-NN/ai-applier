# AI Applier

AI Applier is a job discovery and application preparation platform designed to help early-career software developers find relevant remote opportunities and manage their applications.

The project focuses on making the job search more organized and evidence-based. It brings job discovery, candidate profiles, resume matching, reusable answers, cover-letter drafts, and application preparation into one workspace.

**The platform supports human-reviewed applications. It does not autonomously submit applications to employers.**

## Project goals

The project is working toward helping a candidate discover and prepare for **500 relevant remote junior, graduate, and entry-level software opportunities over eight weeks**.

Its goals are to:

- Aggregate job opportunities from supported sources.
- Help candidates identify roles that match their skills and experience.
- Keep candidate information and application documents organized.
- Reduce repetitive application preparation.
- Make application progress visible and measurable.
- Keep the candidate in control of every application.

## Core features

- **Job discovery:** Collect and browse job listings from supported sources.
- **Candidate profile:** Maintain structured candidate information and skills.
- **Resume management:** Upload and manage candidate resumes.
- **Resume matching:** Calculate deterministic relevance scores using resume and job-description evidence. Scores are not predictions of hiring success.
- **Reusable answers:** Store candidate-authored answers for recurring application questions.
- **Cover-letter drafts:** Generate and manage job-specific cover-letter drafts.
- **Application tracking:** Organize applications and monitor their progress.
- **Application preparation:** Prepare application data and review it before approval.
- **Application campaigns:** Set targets, organize work, and track progress toward a campaign goal.
- **Browser-assisted preparation:** Use the Chrome extension to assist with supported application forms.

Feature availability depends on the supported job source and application form.

## Safety and candidate control

AI Applier is designed around human approval.

- Application information must be reviewed before approval.
- Candidate answers must be confirmed as user-authored before they can be used.
- Preparation and approval do not mean an application has been submitted.
- The platform does not perform unattended bulk application submission.
- The browser extension does not click Submit, solve CAPTCHAs, bypass sign-in, or perform human-verification steps.
- The candidate remains responsible for reviewing and submitting applications.

The system aims to be transparent about what has been discovered, prepared, approved, and actually submitted.

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Authentication | Clerk |
| Backend API | Python, FastAPI |
| Database | PostgreSQL |
| ORM and migrations | SQLAlchemy, Alembic |
| Browser assistance | Chrome extension (Manifest V3) |
| Testing | Pytest, HTTPX, TypeScript and frontend lint/build checks |

## Architecture overview

The application is organized into three main parts:

1. **Frontend (`frontend/`)** — the web dashboard and candidate-facing workflows.
2. **Backend (`backend/`)** — authentication-aware API endpoints, business logic, database models, ingestion workers, and application services.
3. **Chrome extension (`extension/`)** — browser-assisted preparation for supported application forms.

The frontend communicates with the FastAPI backend. The backend persists application and candidate data in PostgreSQL. Database schema changes are managed through Alembic migrations.
