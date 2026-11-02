"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { useAuth, useUser } from "@clerk/nextjs";
import {
  SquaresFour,
  Lightning,
  Files,
  Briefcase,
  ChartPieSlice,
  GearSix,
  MagnifyingGlass,
  Plus,
  ArrowUpRight,
  MapPin,
  Clock,
  TrendUp,
  Binoculars,
  PaperPlaneTilt,
  ChatsCircle,
  CheckCircle,
  CaretRight,
  List,
  Kanban,
  X,
  FileText,
  ListChecks,
  type Icon as PhosphorIcon,
} from "@phosphor-icons/react";
import Navbar from "@/components/Navbar";
import BackendAuthCheck from "@/components/BackendAuthCheck";
import ApplicationBatches from "@/components/ApplicationBatches";
import ApplicationExecutions from "@/components/ApplicationExecutions";
import CoverLetterDrafts from "@/components/CoverLetterDrafts";
import MyDocuments from "@/components/MyDocuments";
import ReusableAnswers from "@/components/ReusableAnswers";
import Insights from "@/components/Insights";

/* -------------------------------------------------------------------------- */
/*  API types                                                                 */
/* -------------------------------------------------------------------------- */

type ApiJob = {
  id: number;
  company: string;
  title: string;
  location: string | null;
  created_at: string;
  source_url: string | null;
  application_url: string | null;
  source_name: string | null;
  source_job_id: string | null;
  expires_at: string | null;
  remote_type: string | null;
  employment_type: string | null;
  experience_level: string;
  eligible_countries: string[] | null;
  eligibility_status: string;
  eligibility_evidence_url: string | null;
  eligibility_evidence: string | null;
  eligibility_verified_at: string | null;
  eligibility_verified_by: string | null;
  listing_status: string;
  listing_status_checked_at: string | null;
  relevance_score?: number;
  matched_role_families?: string[];
  relevance_reasons?: string[];
};

type ApiApplication = {
  id: number;
  job_id: number;
  status: "saved" | "applied" | "interview" | "rejected" | "offer";
  notes: string | null;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
};

type ApiResume = {
  id: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

type ResumeJobMatch = ApiJob & {
  match_score: number;
  matched_terms: string[];
  terms_not_found_in_resume: string[];
  match_reasons: string[];
};

type ResumeJobMatchResult = {
  resume_id: number;
  resume_filename: string;
  items: ResumeJobMatch[];
  total: number;
  skip: number;
  limit: number;
};

type JobSearchResult = {
  items: ApiJob[];
  total: number;
  skip: number;
  limit: number;
};

/* -------------------------------------------------------------------------- */
/*  View-model types                                                          */
/* -------------------------------------------------------------------------- */

type Job = {
  id: number;
  company: string;
  title: string;
  location: string;
  createdAt: string;
  sourceUrl?: string | null;
  sourceName?: string | null;
  sourceJobId?: string | null;
  expiresAt?: string | null;
  listingStatus: string;
  listingStatusCheckedAt: string | null;
  color: string;
  letter: string;
  applicationId: number | null;
  apiStatus: ApiApplication["status"] | null;
  status: "Available" | "Saved" | "Applied" | "Interview" | "Rejected" | "Offer";
  relevanceScore?: number;
  matchedRoleFamilies?: string[];
  relevanceReasons?: string[];
};

type PageName =
  | "Dashboard"
  | "Find Jobs"
  | "Resume Match"
  | "My Documents"
  | "Reusable Answers"
  | "Cover Letter Drafts"
  | "Applications"
  | "Application Batches"
  | "Application Executions"
  | "Insights"
  | "Admin Tools";

type Notice = {
  message: string;
  page?: PageName;
  actionLabel?: string;
} | null;

/* -------------------------------------------------------------------------- */
/*  Navigation: grouped in the order a job seeker actually works               */
/*  Overview → Find work → Prepare → Apply & track                             */
/* -------------------------------------------------------------------------- */

type NavGroup = {
  heading: string;
  adminOnly?: boolean;
  items: { page: PageName; icon: PhosphorIcon }[];
};

const navGroups: NavGroup[] = [
  {
    heading: "Overview",
    items: [{ page: "Dashboard", icon: SquaresFour }],
  },
  {
    heading: "Find work",
    items: [
      { page: "Find Jobs", icon: Binoculars },
      { page: "Resume Match", icon: Lightning },
    ],
  },
  {
    heading: "Prepare",
    items: [
      { page: "My Documents", icon: Files },
      { page: "Reusable Answers", icon: ChatsCircle },
      { page: "Cover Letter Drafts", icon: FileText },
    ],
  },
  {
    heading: "Apply & track",
    items: [
      { page: "Applications", icon: Briefcase },
      { page: "Application Batches", icon: ListChecks },
      { page: "Application Executions", icon: PaperPlaneTilt },
      { page: "Insights", icon: ChartPieSlice },
    ],
  },
  {
    heading: "Admin",
    adminOnly: true,
    items: [{ page: "Admin Tools", icon: GearSix }],
  },
];

const pageMeta: Record<PageName, { title: string; description: string }> = {
  Dashboard: {
    title: "Your career dashboard",
    description: "See where you are and what to do next.",
  },
  "Find Jobs": {
    title: "Find jobs",
    description:
      "Search listings, filter by eligibility, and save the ones you want to pursue.",
  },
  "Resume Match": {
    title: "Resume match",
    description: "Compare your resume with job descriptions to see the overlap.",
  },
  "My Documents": {
    title: "My documents",
    description: "Upload resumes and manage the documents you apply with.",
  },
  "Reusable Answers": {
    title: "Reusable answers",
    description: "Manage your own application answers and approve them before reuse.",
  },
  "Cover Letter Drafts": {
    title: "Cover letter drafts",
    description: "Write and edit cover letters for your saved jobs.",
  },
  Applications: {
    title: "Applications",
    description: "Move every saved job through your pipeline.",
  },
  "Application Batches": {
    title: "Application batches",
    description: "Group applications and prepare them together.",
  },
  "Application Executions": {
    title: "Application executions",
    description: "Follow the progress of submitted applications.",
  },
  Insights: {
    title: "Insights",
    description: "Understand how your job search is going.",
  },
  "Admin Tools": {
    title: "Admin tools",
    description: "Import job listings and add jobs manually.",
  },
};

/** Pages shown directly in the mobile bottom bar. Everything else goes under "More". */
const mobileBarItems: { label: string; page: PageName; icon: PhosphorIcon }[] = [
  { label: "Home", page: "Dashboard", icon: SquaresFour },
  { label: "Jobs", page: "Find Jobs", icon: Binoculars },
  { label: "Applications", page: "Applications", icon: Briefcase },
  { label: "Documents", page: "My Documents", icon: Files },
];

/* -------------------------------------------------------------------------- */
/*  Constants & helpers                                                       */
/* -------------------------------------------------------------------------- */

const companyColors = [
  "bg-indigo-50 text-indigo-700",
  "bg-orange-50 text-orange-700",
  "bg-teal-50 text-teal-700",
  "bg-sky-50 text-sky-700",
  "bg-rose-50 text-rose-700",
  "bg-amber-50 text-amber-700",
];

const statusLabels: Record<ApiApplication["status"], Job["status"]> = {
  saved: "Saved",
  applied: "Applied",
  interview: "Interview",
  rejected: "Rejected",
  offer: "Offer",
};

const pipelineColumns = [
  { name: "Saved", color: "text-slate-500", dot: "bg-slate-400" },
  { name: "Applied", color: "text-violet-600", dot: "bg-violet-500" },
  { name: "Interview", color: "text-amber-600", dot: "bg-amber-500" },
  { name: "Offer", color: "text-emerald-600", dot: "bg-emerald-500" },
  { name: "Rejected", color: "text-rose-600", dot: "bg-rose-500" },
] as const;

const PAGE_SIZE = 20;

async function apiRequest<T>(
  path: string,
  token: string,
  options: RequestInit = {},
): Promise<T> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }

  const response = await fetch(`${apiUrl.replace(/\/$/, "")}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      data && typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status}).`;
    throw new Error(detail);
  }

  return data as T;
}

function toJob(job: ApiJob, application: ApiApplication | undefined): Job {
  return {
    id: job.id,
    company: job.company,
    title: job.title,
    location: job.location || "Location not specified",
    createdAt: new Date(job.created_at).toLocaleDateString(),
    sourceUrl: job.source_url,
    sourceName: job.source_name,
    sourceJobId: job.source_job_id,
    expiresAt: job.expires_at,
    listingStatus: job.listing_status,
    listingStatusCheckedAt: job.listing_status_checked_at,
    color: companyColors[job.id % companyColors.length],
    letter: job.company.trim().charAt(0).toUpperCase() || "J",
    applicationId: application?.id ?? null,
    apiStatus: application?.status ?? null,
    status: application ? statusLabels[application.status] : "Available",
    relevanceScore: job.relevance_score,
    matchedRoleFamilies: job.matched_role_families,
    relevanceReasons: job.relevance_reasons,
  };
}

/* -------------------------------------------------------------------------- */
/*  Small shared components                                                   */
/* -------------------------------------------------------------------------- */

/**
 * One consistent control for tracking a job, used everywhere a job is shown.
 *   not tracked  → "Save job"
 *   saved        → "Mark as applied"
 *   anything else → read-only status badge
 */
function TrackButton({
  application,
  saving,
  onSave,
  onMarkApplied,
}: {
  application: ApiApplication | undefined;
  saving: boolean;
  onSave: () => void;
  onMarkApplied: (applicationId: number) => void;
}) {
  const base =
    "flex w-full items-center justify-center gap-1.5 rounded-xl px-4 py-2.5 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto";

  if (!application) {
    return (
      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className={`${base} bg-violet-600 text-white hover:bg-violet-700`}
      >
        <Plus size={15} />
        {saving ? "Saving…" : "Save job"}
      </button>
    );
  }

  if (application.status === "saved") {
    return (
      <button
        type="button"
        onClick={() => onMarkApplied(application.id)}
        className={`${base} border border-violet-200 bg-white text-violet-700 hover:bg-violet-50`}
      >
        <CheckCircle size={15} />
        Mark as applied
      </button>
    );
  }

  return (
    <span
      className={`${base} cursor-default bg-emerald-50 text-emerald-700`}
      aria-label={`Tracked as ${statusLabels[application.status]}`}
    >
      <CheckCircle size={15} weight="fill" />
      {statusLabels[application.status]}
    </span>
  );
}

function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
      <p className="font-semibold text-slate-800">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
        {description}
      </p>
      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="mt-4 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Kenya eligibility panel (read for everyone, edit for admins)              */
/* -------------------------------------------------------------------------- */

type EligibilityStatus = "eligible" | "ineligible" | "unknown";

function EligibilityVerificationPanel({
  job,
  isAdmin,
  onUpdated,
}: {
  job: ApiJob;
  isAdmin: boolean;
  onUpdated: (updated: ApiJob) => void;
}) {
  const { getToken } = useAuth();

  const [status, setStatus] = useState<EligibilityStatus>(
    job.eligibility_status === "eligible" ||
      job.eligibility_status === "ineligible"
      ? job.eligibility_status
      : "unknown",
  );
  const [evidenceUrl, setEvidenceUrl] = useState(
    job.eligibility_evidence_url ?? "",
  );
  const [evidence, setEvidence] = useState(job.eligibility_evidence ?? "");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const [showForm, setShowForm] = useState(false);

  const statusLabel =
    job.eligibility_status === "eligible"
      ? "Eligible for Kenya"
      : job.eligibility_status === "ineligible"
        ? "Not eligible for Kenya"
        : "Kenya eligibility unverified";

  async function submitVerification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;

    setSaving(true);
    setFormError("");
    setSavedMessage("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApiJob>(
        `/api/jobs/${job.id}/eligibility`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            eligibility_status: status,
            evidence_url: status === "unknown" ? null : evidenceUrl.trim(),
            evidence: status === "unknown" ? null : evidence.trim(),
          }),
        },
      );

      onUpdated(updated);
      setStatus(
        updated.eligibility_status === "eligible" ||
          updated.eligibility_status === "ineligible"
          ? updated.eligibility_status
          : "unknown",
      );
      setEvidenceUrl(updated.eligibility_evidence_url ?? "");
      setEvidence(updated.eligibility_evidence ?? "");
      setSavedMessage("Eligibility verification saved.");
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : "Could not save eligibility verification.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-slate-500">
          Kenya eligibility
        </span>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
            job.eligibility_status === "eligible"
              ? "bg-emerald-50 text-emerald-700"
              : job.eligibility_status === "ineligible"
                ? "bg-red-50 text-red-700"
                : "bg-amber-50 text-amber-700"
          }`}
        >
          {statusLabel}
        </span>
      </div>

      {job.eligibility_evidence && (
        <div className="mt-3 space-y-1 text-sm text-slate-600">
          <p>{job.eligibility_evidence}</p>
          {job.eligibility_evidence_url && (
            <a
              href={job.eligibility_evidence_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block break-all font-medium text-violet-600 underline hover:text-violet-800"
            >
              View verification source
            </a>
          )}
          {job.eligibility_verified_at && (
            <p className="text-xs text-slate-400">
              Verified {new Date(job.eligibility_verified_at).toLocaleString()}
            </p>
          )}
        </div>
      )}

      {isAdmin && (
        <div className="mt-4">
          <button
            type="button"
            onClick={() => {
              setShowForm((visible) => !visible);
              setFormError("");
              setSavedMessage("");
            }}
            aria-expanded={showForm}
            className="inline-flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-700"
          >
            {showForm ? "Close verification" : "Verify Kenya eligibility"}
          </button>

          {showForm && (
            <form onSubmit={submitVerification} className="mt-4 space-y-3">
              <h4 className="text-sm font-bold text-slate-800">
                Admin verification
              </h4>

              <label className="block text-sm font-medium text-slate-700">
                Decision
                <select
                  value={status}
                  onChange={(event) =>
                    setStatus(event.target.value as EligibilityStatus)
                  }
                  disabled={saving}
                  className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"
                >
                  <option value="unknown">Unknown / clear verification</option>
                  <option value="eligible">Eligible to work from Kenya</option>
                  <option value="ineligible">Not eligible from Kenya</option>
                </select>
              </label>

              {status !== "unknown" && (
                <>
                  <label className="block text-sm font-medium text-slate-700">
                    Evidence source URL *
                    <input
                      type="url"
                      required
                      maxLength={2048}
                      value={evidenceUrl}
                      onChange={(event) => setEvidenceUrl(event.target.value)}
                      disabled={saving}
                      placeholder="https://company.com/careers/eligibility"
                      className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                    />
                  </label>

                  <label className="block text-sm font-medium text-slate-700">
                    Supporting evidence *
                    <textarea
                      required
                      maxLength={10000}
                      rows={3}
                      value={evidence}
                      onChange={(event) => setEvidence(event.target.value)}
                      disabled={saving}
                      placeholder="Explain what the source confirms about applicants based in Kenya."
                      className="mt-1.5 w-full resize-y rounded-lg border border-slate-200 px-3 py-2.5 text-sm font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                    />
                  </label>
                </>
              )}

              {formError && (
                <p role="alert" className="text-sm text-red-600">
                  {formError}
                </p>
              )}
              {savedMessage && (
                <p role="status" className="text-sm text-emerald-700">
                  {savedMessage}
                </p>
              )}

              <button
                type="submit"
                disabled={saving}
                className="rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {saving ? "Saving verification..." : "Save verification"}
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Employer application URL (admin only)                                     */
/* -------------------------------------------------------------------------- */

function ApplicationUrlPanel({
  job,
  onUpdated,
}: {
  job: ApiJob;
  onUpdated: (updated: ApiJob) => void;
}) {
  const { getToken } = useAuth();

  const [applicationUrl, setApplicationUrl] = useState(
    job.application_url ?? "",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [showForm, setShowForm] = useState(false);

  async function saveApplicationUrl(clear = false) {
    if (saving) return;

    const value = clear ? null : applicationUrl.trim();

    if (!clear) {
      if (!value) {
        setError("Enter an employer application URL.");
        return;
      }

      try {
        const parsed = new URL(value);
        if (parsed.protocol !== "https:") {
          throw new Error("The employer application URL must use HTTPS.");
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Enter a valid HTTPS URL.",
        );
        return;
      }
    }

    setSaving(true);
    setError("");
    setMessage("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApiJob>(
        `/api/jobs/${job.id}/application-url`,
        token,
        {
          method: "PATCH",
          body: JSON.stringify({ application_url: value }),
        },
      );

      setApplicationUrl(updated.application_url ?? "");
      onUpdated(updated);
      setMessage(
        clear
          ? "Employer application URL cleared."
          : "Employer application URL saved.",
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not update the application URL.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-slate-500">
          Employer application URL
        </span>

        {job.application_url ? (
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700">
            Provided
          </span>
        ) : (
          <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
            Not provided — review only
          </span>
        )}
      </div>

      {job.application_url && (
        <a
          href={job.application_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block break-all text-sm font-medium text-violet-700 underline"
        >
          Open employer application page
        </a>
      )}

      <button
        type="button"
        onClick={() => {
          setApplicationUrl(job.application_url ?? "");
          setShowForm((visible) => !visible);
          setError("");
          setMessage("");
        }}
        aria-expanded={showForm}
        className="mt-3 block rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700"
      >
        {showForm ? "Close URL editor" : "Manage application URL"}
      </button>

      {showForm && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void saveApplicationUrl();
          }}
          className="mt-4 space-y-3"
        >
          <label className="block text-sm font-medium text-slate-700">
            Verified employer application URL
            <input
              type="url"
              required
              maxLength={2048}
              value={applicationUrl}
              onChange={(event) => setApplicationUrl(event.target.value)}
              disabled={saving}
              placeholder="https://boards.greenhouse.io/company/jobs/123"
              className="mt-1.5 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
            />
          </label>

          <p className="text-xs text-slate-500">
            Enter the actual employer application page, not the job
            discovery listing. Only HTTPS URLs are accepted.
          </p>

          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}

          {message && (
            <p role="status" className="text-sm text-emerald-700">
              {message}
            </p>
          )}

          <div className="flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={saving || !applicationUrl.trim()}
              className="rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? "Saving..." : "Save URL"}
            </button>

            {job.application_url && (
              <button
                type="button"
                disabled={saving}
                onClick={() => void saveApplicationUrl(true)}
                className="rounded-lg border border-red-200 px-4 py-2.5 text-sm font-semibold text-red-600 hover:bg-red-50 disabled:opacity-60"
              >
                Clear URL
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  Job card (Find Jobs list)                                                 */
/* -------------------------------------------------------------------------- */

function JobCard({
  job,
  apiJob,
  application,
  saving,
  isAdmin,
  onSave,
  onMarkApplied,
  onEligibilityUpdated,
}: {
  job: Job;
  apiJob: ApiJob;
  application: ApiApplication | undefined;
  saving: boolean;
  isAdmin: boolean;
  onSave: () => void;
  onMarkApplied: (applicationId: number) => void;
  onEligibilityUpdated: (updated: ApiJob) => void;
}) {
  return (
    <article className="rounded-2xl border border-slate-200/80 bg-white p-4 transition hover:border-violet-200 sm:p-5">
      <div className="flex flex-wrap items-start gap-3">
        <div
          className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-lg font-extrabold ${job.color}`}
        >
          {job.letter}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-bold text-slate-900">{job.title}</h3>
            {job.applicationId !== null && (
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-bold text-emerald-700">
                {job.status}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-slate-600">{job.company}</p>

          {(job.sourceName || job.sourceUrl) && (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              {job.sourceName && (
                <span className="text-slate-500">
                  Source: {job.sourceName}
                </span>
              )}
              {job.sourceUrl && (
                <a
                  href={job.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold text-violet-700 underline decoration-violet-300 underline-offset-2 hover:text-violet-900"
                >
                  View listing{job.sourceName ? ` on ${job.sourceName}` : ""}
                </a>
              )}
            </div>
          )}

          {job.relevanceScore !== undefined && (
            <div className="mt-3 rounded-xl border border-violet-100 bg-violet-50/70 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs font-semibold text-violet-900">
                  Role relevance
                </p>
                <span className="rounded-full bg-white px-2.5 py-1 text-xs font-bold text-violet-800">
                  {job.relevanceScore}/100
                </span>
              </div>

              {job.matchedRoleFamilies && job.matchedRoleFamilies.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {job.matchedRoleFamilies.map((family) => (
                    <span
                      key={family}
                      className="rounded-full border border-violet-200 bg-white px-2 py-1 text-[11px] font-medium text-violet-800"
                    >
                      {family}
                    </span>
                  ))}
                </div>
              )}

              {job.relevanceReasons && job.relevanceReasons.length > 0 && (
                <ul className="mt-2 space-y-1 text-xs text-slate-600">
                  {job.relevanceReasons.map((reason, index) => (
                    <li key={`${index}-${reason}`}>{reason}</li>
                  ))}
                </ul>
              )}

              <p className="mt-2 text-[11px] text-slate-500">
                Role match only; this does not confirm hiring eligibility.
              </p>
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
            <span className="flex items-center gap-1.5">
              <MapPin size={14} />
              {job.location}
            </span>
            <span className="flex items-center gap-1.5">
              <Clock size={14} />
              Added {job.createdAt}
            </span>
            <span>Listing: {job.listingStatus}</span>
            <span>
              Status checked:{" "}
              {job.listingStatusCheckedAt
                ? new Date(job.listingStatusCheckedAt).toLocaleString()
                : "Not checked yet"}
            </span>
          </div>
        </div>

        <TrackButton
          application={application}
          saving={saving}
          onSave={onSave}
          onMarkApplied={onMarkApplied}
        />
      </div>

      <EligibilityVerificationPanel
        job={apiJob}
        isAdmin={isAdmin}
        onUpdated={onEligibilityUpdated}
      />

      {isAdmin && (
        <ApplicationUrlPanel
          job={apiJob}
          onUpdated={onEligibilityUpdated}
        />
      )}
    </article>
  );
}

/* -------------------------------------------------------------------------- */
/*  Resume match card (Resume Match results)                                  */
/* -------------------------------------------------------------------------- */

function ResumeMatchCard({
  match,
  application,
  saving,
  onSave,
  onMarkApplied,
}: {
  match: ResumeJobMatch;
  application: ApiApplication | undefined;
  saving: boolean;
  onSave: () => void;
  onMarkApplied: (applicationId: number) => void;
}) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h4 className="font-bold text-slate-900">{match.title}</h4>
          <p className="mt-1 text-sm text-slate-600">
            {match.company}
            {match.location ? ` · ${match.location}` : ""}
          </p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700">
              Listing: {match.listing_status}
            </span>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium text-slate-700">
              Kenya eligibility: {match.eligibility_status}
            </span>
          </div>
        </div>

        <div className="shrink-0 rounded-xl bg-violet-50 px-4 py-3 text-center">
          <p className="text-2xl font-extrabold text-violet-800">
            {match.match_score}
            <span className="text-sm">/100</span>
          </p>
          <p className="text-xs font-semibold text-violet-700">Text match</p>
        </div>
      </div>

      {match.match_reasons.length > 0 && (
        <ul className="mt-4 space-y-1 text-sm text-slate-600">
          {match.match_reasons.map((reason, index) => (
            <li key={`${index}-${reason}`}>{reason}</li>
          ))}
        </ul>
      )}

      {match.matched_terms.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-bold tracking-wide text-slate-500 uppercase">
            Terms found in your resume
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {match.matched_terms.map((term) => (
              <span
                key={term}
                className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800"
              >
                {term}
              </span>
            ))}
          </div>
        </div>
      )}

      {match.terms_not_found_in_resume.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-bold tracking-wide text-slate-500 uppercase">
            Terms not found in your resume
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {match.terms_not_found_in_resume.map((term) => (
              <span
                key={term}
                className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800"
              >
                {term}
              </span>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">
            These terms may be absent from the document text; this does not
            prove you lack the skills.
          </p>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {match.source_url && (
          <a
            href={match.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-semibold text-violet-700 underline underline-offset-2"
          >
            View job listing
          </a>
        )}
        <TrackButton
          application={application}
          saving={saving}
          onSave={onSave}
          onMarkApplied={onMarkApplied}
        />
      </div>
    </article>
  );
}

/* -------------------------------------------------------------------------- */
/*  Page                                                                      */
/* -------------------------------------------------------------------------- */

const emptyJobForm = {
  title: "",
  company: "",
  location: "",
  employment_type: "",
  source_url: "",
  description: "",
};

export default function DashboardPage() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();

  /* ---- navigation / feedback ---- */
  const [activePage, setActivePage] = useState<PageName>("Dashboard");
  const [draftToOpenId, setDraftToOpenId] = useState<number | null>(null);
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  /* ---- Find Jobs ---- */
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [remoteType, setRemoteType] = useState("");
  const [employmentType, setEmploymentType] = useState("");
  const [experienceLevel, setExperienceLevel] = useState("");
  const [eligibilityStatus, setEligibilityStatus] = useState("");
  const [listingStatus, setListingStatus] = useState("");
  const [sortBy, setSortBy] = useState<"newest" | "relevance">("newest");
  const [jobPage, setJobPage] = useState(1);
  const [jobTotal, setJobTotal] = useState(0);
  const [availableJobCount, setAvailableJobCount] = useState(0);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsRefreshKey, setJobsRefreshKey] = useState(0);
  const [apiJobs, setApiJobs] = useState<ApiJob[]>([]);

  /* ---- Resume Match ---- */
  const [resumes, setResumes] = useState<ApiResume[]>([]);
  const [selectedResumeId, setSelectedResumeId] = useState("");
  const [resumeMatches, setResumeMatches] =
    useState<ResumeJobMatchResult | null>(null);
  const [resumesLoading, setResumesLoading] = useState(false);
  const [matchingLoading, setMatchingLoading] = useState(false);
  const [resumeMatchError, setResumeMatchError] = useState("");
  const [resumeMatchNotice, setResumeMatchNotice] = useState("");

  /* ---- Applications ---- */
  const [applications, setApplications] = useState<ApiApplication[]>([]);
  const [trackedApiJobs, setTrackedApiJobs] = useState<ApiJob[]>([]);
  const [view, setView] = useState<"board" | "list">("board");
  const [savingJobId, setSavingJobId] = useState<number | null>(null);

  /* ---- Admin ---- */
  const [isImportingJobicy, setIsImportingJobicy] = useState(false);
  const [isImportingHimalayas, setIsImportingHimalayas] = useState(false);
  const [creatingJob, setCreatingJob] = useState(false);
  const [jobFormError, setJobFormError] = useState("");
  const [jobForm, setJobForm] = useState(emptyJobForm);

  /* ---- Dashboard activity chart ---- */
  const [activity, setActivity] = useState<
    { day: string; count: number; height: number }[]
  >([]);

  const dashboardLoading = !isLoaded || (isSignedIn === true && loading);
  const dashboardError = !isLoaded
    ? ""
    : !isSignedIn
      ? "Sign in to load your jobs and applications."
      : error;

  /* ------------------------------------------------------------------------ */
  /*  Navigation                                                              */
  /* ------------------------------------------------------------------------ */

  const loadResumes = useCallback(async () => {
    setResumesLoading(true);
    setResumeMatchError("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const result = await apiRequest<ApiResume[]>("/api/resumes", token);
      setResumes(result);

      setSelectedResumeId((current) => {
        if (current && result.some((resume) => String(resume.id) === current)) {
          return current;
        }
        return result[0] ? String(result[0].id) : "";
      });
    } catch (err) {
      setResumeMatchError(
        err instanceof Error ? err.message : "Could not load your resumes.",
      );
    } finally {
      setResumesLoading(false);
    }
  }, [getToken]);

  /** The single way to change pages: clears stale messages and refreshes what the next page needs. */
  const goTo = useCallback(
    (page: PageName) => {
      setActivePage(page);
      setMobileMoreOpen(false);
      setNotice(null);
      setError("");
      setDraftToOpenId(null);

      // Resumes may have been uploaded in My Documents, so refresh when they matter.
      if (page === "Dashboard" || page === "Resume Match") {
        void loadResumes();
      }

      if (typeof window !== "undefined") {
        window.scrollTo({ top: 0 });
      }
    },
    [loadResumes],
  );

  function showNotice(message: string, page?: PageName, actionLabel?: string) {
    setNotice({ message, page, actionLabel });
  }

  function openDraftEditor(draftId?: number | null) {
    setActivePage("Cover Letter Drafts");
    setDraftToOpenId(draftId ?? null);
    setMobileMoreOpen(false);
    setNotice(null);
    window.scrollTo({ top: 0 });
  }

  /* ------------------------------------------------------------------------ */
  /*  Data loading                                                            */
  /* ------------------------------------------------------------------------ */

  // Applications, admin status and resumes load once on sign-in.
  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

    let cancelled = false;

    async function loadData() {
      setLoading(true);
      setError("");

      try {
        const token = await getToken();
        if (!token) {
          throw new Error("No Clerk session token is available.");
        }

        const [loadedApplications, hasAdminAccess, loadedResumes] =
          await Promise.all([
            apiRequest<ApiApplication[]>("/api/applications?limit=100", token),
            apiRequest<{ is_admin: boolean }>("/api/admin/status", token)
              .then((result) => result.is_admin)
              .catch(() => false),
            apiRequest<ApiResume[]>("/api/resumes", token).catch(
              () => [] as ApiResume[],
            ),
          ]);

        if (!cancelled) {
          setApplications(loadedApplications);
          setIsAdmin(hasAdminAccess);
          setResumes(loadedResumes);
          setSelectedResumeId(
            (current) =>
              current || (loadedResumes[0] ? String(loadedResumes[0].id) : ""),
          );
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load dashboard data.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadData();

    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken]);

  // Total number of listings, independent of any filters (for the dashboard).
  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

    let cancelled = false;

    async function loadAvailableCount() {
      try {
        const token = await getToken();
        if (!token) return;

        const params = new URLSearchParams({
          q: "",
          skip: "0",
          limit: "1",
          sort_by: "newest",
        });

        const result = await apiRequest<JobSearchResult>(
          `/api/jobs/search?${params.toString()}`,
          token,
        );

        if (!cancelled) setAvailableJobCount(result.total);
      } catch {
        // Non-critical: the dashboard simply keeps its previous count.
      }
    }

    void loadAvailableCount();

    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken, jobsRefreshKey]);

  // Debounce the search box.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search.trim());
    }, 300);

    return () => clearTimeout(timer);
  }, [search]);

  // Job listings are only fetched while the Find Jobs page is open.
  useEffect(() => {
    if (!isLoaded || !isSignedIn || activePage !== "Find Jobs") return;

    let cancelled = false;

    async function loadJobs() {
      setJobsLoading(true);

      try {
        const token = await getToken();
        if (!token) {
          throw new Error("No Clerk session token is available.");
        }

        const params = new URLSearchParams({
          q: debouncedSearch,
          skip: String((jobPage - 1) * PAGE_SIZE),
          limit: String(PAGE_SIZE),
          sort_by: sortBy,
        });

        if (remoteType) params.set("remote_type", remoteType);
        if (employmentType) params.set("employment_type", employmentType);
        if (experienceLevel) params.set("experience_level", experienceLevel);
        if (eligibilityStatus) {
          params.set("eligibility_status", eligibilityStatus);
        }
        if (listingStatus) params.set("listing_status", listingStatus);

        const result = await apiRequest<JobSearchResult>(
          `/api/jobs/search?${params.toString()}`,
          token,
        );

        if (!cancelled) {
          setApiJobs(result.items);
          setJobTotal(result.total);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load jobs.");
        }
      } finally {
        if (!cancelled) setJobsLoading(false);
      }
    }

    void loadJobs();

    return () => {
      cancelled = true;
    };
  }, [
    isLoaded,
    isSignedIn,
    getToken,
    activePage,
    debouncedSearch,
    jobPage,
    jobsRefreshKey,
    remoteType,
    employmentType,
    experienceLevel,
    eligibilityStatus,
    listingStatus,
    sortBy,
  ]);

  // Load the job details behind each application. Keyed by job ids, so a
  // status change does not trigger a refetch of every tracked job.
  const trackedJobIdsKey = useMemo(
    () =>
      [...new Set(applications.map((item) => item.job_id))]
        .sort((a, b) => a - b)
        .join(","),
    [applications],
  );

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

    let cancelled = false;

    async function loadTrackedJobs() {
      try {
        const token = await getToken();
        if (!token) {
          throw new Error("No Clerk session token is available.");
        }

        const jobIds = trackedJobIdsKey
          ? trackedJobIdsKey.split(",").map(Number)
          : [];

        const loadedJobs = await Promise.all(
          jobIds.map((jobId) => apiRequest<ApiJob>(`/api/jobs/${jobId}`, token)),
        );

        if (!cancelled) setTrackedApiJobs(loadedJobs);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load tracked application jobs.",
          );
        }
      }
    }

    void loadTrackedJobs();

    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken, trackedJobIdsKey]);

  // Weekly activity bars.
  useEffect(() => {
    const days = Array.from({ length: 7 }, (_, index) => {
      const date = new Date();
      date.setHours(0, 0, 0, 0);
      date.setDate(date.getDate() - (6 - index));

      const nextDay = new Date(date);
      nextDay.setDate(nextDay.getDate() + 1);

      const count = applications.filter((application) => {
        const created = new Date(application.created_at);
        return created >= date && created < nextDay;
      }).length;

      return {
        day: date.toLocaleDateString("en", { weekday: "short" }),
        count,
      };
    });

    const maximum = Math.max(...days.map((day) => day.count), 1);

    const frame = window.requestAnimationFrame(() => {
      setActivity(
        days.map((day) => ({
          ...day,
          height:
            day.count === 0 ? 0 : Math.max(8, (day.count / maximum) * 100),
        })),
      );
    });

    return () => window.cancelAnimationFrame(frame);
  }, [applications]);

  /* ------------------------------------------------------------------------ */
  /*  Derived data                                                            */
  /* ------------------------------------------------------------------------ */

  const applicationByJobId = useMemo(() => {
    const map = new Map<number, ApiApplication>();
    for (const application of applications) {
      map.set(application.job_id, application);
    }
    return map;
  }, [applications]);

  const jobCards = useMemo(
    () =>
      apiJobs.map((apiJob) => ({
        apiJob,
        job: toJob(apiJob, applicationByJobId.get(apiJob.id)),
      })),
    [apiJobs, applicationByJobId],
  );

  const trackedJobs = useMemo<Job[]>(
    () =>
      trackedApiJobs.flatMap((job) => {
        const application = applicationByJobId.get(job.id);
        return application ? [toJob(job, application)] : [];
      }),
    [trackedApiJobs, applicationByJobId],
  );

  const recentApplications = useMemo(
    () =>
      applications
        .slice(0, 5)
        .map((application) =>
          trackedJobs.find((job) => job.applicationId === application.id),
        )
        .filter((job): job is Job => job !== undefined),
    [applications, trackedJobs],
  );

  const visibleNavGroups = useMemo(
    () => navGroups.filter((group) => !group.adminOnly || isAdmin),
    [isAdmin],
  );

  const mobileMoreItems = useMemo(
    () =>
      visibleNavGroups
        .flatMap((group) => group.items)
        .filter(
          (item) => !mobileBarItems.some((bar) => bar.page === item.page),
        ),
    [visibleNavGroups],
  );

  const currentGroup =
    navGroups.find((group) =>
      group.items.some((item) => item.page === activePage),
    )?.heading ?? "";

  const totalPages = Math.max(1, Math.ceil(jobTotal / PAGE_SIZE));
  const firstResult = jobTotal === 0 ? 0 : (jobPage - 1) * PAGE_SIZE + 1;
  const lastResult = Math.min(jobPage * PAGE_SIZE, jobTotal);

  const hasActiveFilters = Boolean(
    remoteType || employmentType || experienceLevel || eligibilityStatus || listingStatus || search || sortBy !== "newest",
  );

  const stats = [
    {
      label: "Available jobs",
      value: String(availableJobCount),
      delta: "Browse all listings",
      icon: Binoculars,
      style: "bg-indigo-50 text-indigo-600",
      page: "Find Jobs" as PageName,
    },
    {
      label: "Applications",
      value: String(applications.length),
      delta: "Jobs you are tracking",
      icon: PaperPlaneTilt,
      style: "bg-violet-50 text-violet-600",
      page: "Applications" as PageName,
    },
    {
      label: "Interviews",
      value: String(
        applications.filter((app) => app.status === "interview").length,
      ),
      delta: "Recorded interviews",
      icon: ChatsCircle,
      style: "bg-amber-50 text-amber-600",
      page: "Applications" as PageName,
    },
    {
      label: "Offers",
      value: String(
        applications.filter((app) => app.status === "offer").length,
      ),
      delta: "Recorded offers",
      icon: ChartPieSlice,
      style: "bg-emerald-50 text-emerald-600",
      page: "Applications" as PageName,
    },
  ];

  const nextSteps: {
    title: string;
    description: string;
    cta: string;
    page: PageName;
    done?: boolean;
  }[] = [
    {
      title: "Upload your resume",
      description: "Add a PDF or DOCX so you can match and apply with it.",
      cta: "Upload resume",
      page: "My Documents",
      done: resumes.length > 0,
    },
    {
      title: "Find and save jobs",
      description: "Search listings and save the ones worth pursuing.",
      cta: "Browse jobs",
      page: "Find Jobs",
      done: applications.length > 0,
    },
    {
      title: "Check your resume fit",
      description: "See which job terms appear in your resume and which do not.",
      cta: "Match resume",
      page: "Resume Match",
      done: resumeMatches !== null,
    },
    {
      title: "Draft cover letters",
      description: "Prepare a tailored cover letter for each saved job.",
      cta: "Open drafts",
      page: "Cover Letter Drafts",
    },
    {
      title: "Track your applications",
      description: "Move jobs to Applied, Interview, or Offer as things progress.",
      cta: "View pipeline",
      page: "Applications",
      done: applications.some((app) => app.status !== "saved"),
    },
  ];

  const nextStepCard =
    resumes.length === 0
      ? {
          text: "Start by adding a resume so you can match and apply.",
          cta: "Upload your resume",
          page: "My Documents" as PageName,
        }
      : applications.length === 0
        ? {
            text: "Your resume is ready. Find jobs to save to your pipeline.",
            cta: "Find jobs",
            page: "Find Jobs" as PageName,
          }
        : {
            text: "Keep your pipeline up to date as applications progress.",
            cta: "Open applications",
            page: "Applications" as PageName,
          };

  const profileName =
    user?.fullName ||
    user?.primaryEmailAddress?.emailAddress ||
    "Your profile";
  const profileInitials =
    (user?.firstName?.charAt(0) ?? "") + (user?.lastName?.charAt(0) ?? "") ||
    profileName.charAt(0).toUpperCase();

  /* ------------------------------------------------------------------------ */
  /*  Actions                                                                 */
  /* ------------------------------------------------------------------------ */

  async function changeStatus(
    applicationId: number,
    nextStatus: ApiApplication["status"],
  ) {
    setError("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApiApplication>(
        `/api/applications/${applicationId}`,
        token,
        {
          method: "PATCH",
          body: JSON.stringify({ status: nextStatus }),
        },
      );

      setApplications((current) =>
        current.map((application) =>
          application.id === updated.id ? updated : application,
        ),
      );

      showNotice(
        `Application moved to ${statusLabels[nextStatus]}.`,
        activePage === "Applications" ? undefined : "Applications",
        activePage === "Applications" ? undefined : "View applications",
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not update application.",
      );
    }
  }

  async function saveJob(jobId: number) {
    if (savingJobId !== null) return;

    if (applicationByJobId.has(jobId)) {
      showNotice("This job is already in your pipeline.", "Applications", "View applications");
      return;
    }

    setSavingJobId(jobId);
    setError("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const created = await apiRequest<ApiApplication>(
        "/api/applications",
        token,
        {
          method: "POST",
          body: JSON.stringify({ job_id: jobId, notes: null }),
        },
      );

      setApplications((current) => [created, ...current]);
      showNotice("Job saved to your pipeline.", "Applications", "View applications");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save this job.");
    } finally {
      setSavingJobId(null);
    }
  }

  async function matchJobsToResume() {
    if (!selectedResumeId || matchingLoading) return;

    setMatchingLoading(true);
    setResumeMatchError("");
    setResumeMatchNotice("");
    setResumeMatches(null);

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const params = new URLSearchParams({
        resume_id: selectedResumeId,
        skip: "0",
        limit: "100",
      });

      const result = await apiRequest<ResumeJobMatchResult>(
        `/api/jobs/matches?${params.toString()}`,
        token,
      );

      setResumeMatches(result);
      setResumeMatchNotice(
        result.total === 0
          ? "No jobs are available to match yet."
          : `Matched ${result.total} jobs against ${result.resume_filename}.`,
      );
    } catch (err) {
      setResumeMatchError(
        err instanceof Error
          ? err.message
          : "Could not match jobs to your resume.",
      );
    } finally {
      setMatchingLoading(false);
    }
  }

  async function importJobicy() {
    if (isImportingJobicy) return;

    setIsImportingJobicy(true);
    setError("");
    setNotice(null);

    try {
      const token = await getToken();
      if (!token) {
        throw new Error("Your session has expired. Please sign in again.");
      }

      const result = await apiRequest<{
        fetched: number;
        inserted: number;
        updated: number;
      }>("/api/jobs/ingest/jobicy", token, { method: "POST" });

      setJobPage(1);
      setJobsRefreshKey((current) => current + 1);
      showNotice(
        `Jobicy import complete: ${result.fetched} fetched, ` +
          `${result.inserted} inserted, ${result.updated} updated.`,
        "Find Jobs",
        "View jobs",
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not import Jobicy jobs.",
      );
    } finally {
      setIsImportingJobicy(false);
    }
  }

  async function importHimalayas() {
    if (isImportingHimalayas) return;

    setIsImportingHimalayas(true);
    setError("");
    setNotice(null);

    try {
      const token = await getToken();
      if (!token) {
        throw new Error("Your session has expired. Please sign in again.");
      }

      let completed = false;
      let batches = 0;
      let pagesFetched = 0;
      let fetched = 0;
      let inserted = 0;
      let updated = 0;
      let expired = 0;

      while (!completed) {
        const result = await apiRequest<{
          status: "running" | "completed";
          pages_this_batch: number;
          fetched_this_batch: number;
          inserted_this_batch: number;
          updated_this_batch: number;
          expired_this_batch: number;
          pages_fetched: number;
          fetched: number;
          inserted: number;
          updated: number;
          expired: number;
          completed: boolean;
        }>("/api/jobs/ingest/himalayas/batch?max_pages=5", token, {
          method: "POST",
        });

        batches += 1;
        pagesFetched += result.pages_this_batch;
        fetched += result.fetched_this_batch;
        inserted += result.inserted_this_batch;
        updated += result.updated_this_batch;
        expired += result.expired_this_batch;
        completed = result.completed;

        showNotice(
          `Himalayas import in progress: ${fetched} fetched across ` +
            `${batches} batches (${pagesFetched} pages).`,
        );
      }

      setJobPage(1);
      setJobsRefreshKey((current) => current + 1);
      showNotice(
        `Himalayas import complete: ${fetched} fetched, ` +
          `${inserted} inserted, ${updated} updated, ${expired} expired.`,
        "Find Jobs",
        "View jobs",
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not import Himalayas jobs.",
      );
    } finally {
      setIsImportingHimalayas(false);
    }
  }

  async function createJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (creatingJob) return;

    setCreatingJob(true);
    setJobFormError("");
    setError("");

    try {
      const token = await getToken();
      if (!token) {
        throw new Error("Your session has expired. Please sign in again.");
      }

      await apiRequest<ApiJob>("/api/jobs", token, {
        method: "POST",
        body: JSON.stringify({
          title: jobForm.title.trim(),
          company: jobForm.company.trim(),
          location: jobForm.location.trim() || null,
          employment_type: jobForm.employment_type || null,
          source_url: jobForm.source_url.trim() || null,
          description: jobForm.description.trim() || null,
        }),
      });

      setJobPage(1);
      setJobsRefreshKey((current) => current + 1);
      setJobForm(emptyJobForm);
      showNotice("Job added successfully.", "Find Jobs", "View jobs");
    } catch (err) {
      setJobFormError(
        err instanceof Error ? err.message : "Could not create the job.",
      );
    } finally {
      setCreatingJob(false);
    }
  }

  function updateJobFilter(apply: () => void) {
    apply();
    setJobPage(1);
  }

  function clearJobFilters() {
    setRemoteType("");
    setEmploymentType("");
    setExperienceLevel("");
    setEligibilityStatus("");
    setListingStatus("");
    setSortBy("newest");
    setSearch("");
    setJobPage(1);
  }

  function handleEligibilityUpdated(updated: ApiJob) {
    setApiJobs((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    );
    setTrackedApiJobs((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    );
  }

  /* ------------------------------------------------------------------------ */
  /*  Render                                                                  */
  /* ------------------------------------------------------------------------ */

  const meta = pageMeta[activePage];
  const trackedStillLoading =
    applications.length > 0 && trackedJobs.length === 0;

  return (
    <>
      <Navbar />
      <div className="min-h-dvh pt-[68px]">
        <div className="flex min-h-[calc(100dvh-68px)]">
          {/* ------------------------------ Sidebar ------------------------------ */}
          <aside className="hidden w-64 shrink-0 flex-col bg-[#101323] text-white lg:sticky lg:top-[68px] lg:flex lg:h-[calc(100dvh-68px)] lg:overflow-y-auto">
            <div className="mx-4 my-6 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-violet-500/20 text-sm font-bold text-violet-200">
                  {profileInitials}
                </div>
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">
                    {profileName}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">Free workspace</p>
                </div>
              </div>
            </div>

            <nav
              aria-label="Dashboard navigation"
              className="flex-1 space-y-5 px-3 pb-4"
            >
              {visibleNavGroups.map((group) => (
                <div key={group.heading}>
                  <p className="px-4 pb-2 text-[10px] font-bold tracking-[0.18em] text-slate-500 uppercase">
                    {group.heading}
                  </p>
                  <div className="space-y-1">
                    {group.items.map(({ page, icon: Icon }) => (
                      <button
                        key={page}
                        type="button"
                        onClick={() => goTo(page)}
                        aria-current={activePage === page ? "page" : undefined}
                        className={`flex w-full items-center gap-3 rounded-xl px-4 py-2.5 text-left text-sm transition ${
                          activePage === page
                            ? "sidebar-active font-semibold"
                            : "text-slate-400 hover:bg-white/5 hover:text-white"
                        }`}
                      >
                        <Icon size={20} weight="duotone" />
                        <span className="flex-1">{page}</span>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </nav>

            {!dashboardLoading && isSignedIn && (
              <div className="m-4 rounded-2xl border border-white/10 bg-gradient-to-br from-violet-500/15 to-transparent p-4">
                <div className="mb-3 flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-emerald-400" />
                  <span className="text-xs font-semibold text-slate-200">
                    Next step
                  </span>
                </div>
                <p className="text-xs leading-relaxed text-slate-400">
                  {nextStepCard.text}
                </p>
                <button
                  type="button"
                  onClick={() => goTo(nextStepCard.page)}
                  className="mt-4 flex items-center gap-2 text-xs font-bold text-violet-300 hover:text-white"
                >
                  {nextStepCard.cta}
                  <CaretRight size={14} />
                </button>
              </div>
            )}
          </aside>

          {/* ------------------------------- Main -------------------------------- */}
          <main className="flex min-w-0 flex-1 flex-col">
            <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200/70 bg-white px-5 py-4 sm:px-8 sm:py-5 lg:px-10">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-violet-600">
                    {currentGroup}
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">
                    {dashboardLoading
                      ? "Loading"
                      : dashboardError
                        ? "Connection issue"
                        : "Live data"}
                  </span>
                </div>
                <h1 className="mt-2 text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">
                  {meta.title}
                </h1>
                <p className="mt-1 hidden text-sm text-slate-500 sm:block">
                  {meta.description}
                </p>
              </div>

              <div className="flex w-full items-center gap-2 sm:w-auto sm:gap-3">
                {activePage === "Find Jobs" && (
                  <label className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 focus-within:border-violet-300 sm:w-64 sm:flex-none">
                    <MagnifyingGlass
                      size={18}
                      className="shrink-0 text-slate-400"
                    />
                    <input
                      value={search}
                      onChange={(event) => {
                        setSearch(event.target.value);
                        setJobPage(1);
                      }}
                      placeholder="Search by title or company"
                      aria-label="Search jobs"
                      className="w-full min-w-0 bg-transparent text-base outline-none placeholder:text-slate-400 sm:text-sm"
                    />
                    {search && (
                      <button
                        type="button"
                        onClick={() => {
                          setSearch("");
                          setJobPage(1);
                        }}
                        aria-label="Clear search"
                        className="text-slate-400 hover:text-slate-700"
                      >
                        <X size={15} />
                      </button>
                    )}
                  </label>
                )}

                {activePage !== "Find Jobs" && (
                  <button
                    type="button"
                    onClick={() => goTo("Find Jobs")}
                    className="flex shrink-0 items-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-violet-200 transition hover:bg-violet-700"
                  >
                    <MagnifyingGlass size={18} />
                    <span>Find jobs</span>
                  </button>
                )}
              </div>
            </header>

            {notice && (
              <div
                role="status"
                className="mx-5 mt-4 flex items-center justify-between gap-3 rounded-xl border border-violet-100 bg-violet-50 px-4 py-3 text-sm text-violet-800 sm:mx-8 lg:mx-10"
              >
                <span className="min-w-0">
                  {notice.message}
                  {notice.page && notice.actionLabel && (
                    <button
                      type="button"
                      onClick={() => goTo(notice.page as PageName)}
                      className="ml-2 font-bold underline underline-offset-2 hover:text-violet-950"
                    >
                      {notice.actionLabel}
                    </button>
                  )}
                </span>
                <button
                  type="button"
                  onClick={() => setNotice(null)}
                  aria-label="Dismiss notification"
                  className="shrink-0"
                >
                  <X size={16} />
                </button>
              </div>
            )}

            {dashboardError && (
              <div
                role="alert"
                className="mx-5 mt-4 flex items-start justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 sm:mx-8 lg:mx-10"
              >
                <span className="min-w-0">{dashboardError}</span>
                {error && (
                  <button
                    type="button"
                    onClick={() => setError("")}
                    aria-label="Dismiss error"
                    className="shrink-0"
                  >
                    <X size={16} />
                  </button>
                )}
              </div>
            )}

            {dashboardLoading && (
              <p
                role="status"
                className="px-5 pt-4 text-sm text-slate-500 sm:px-8 lg:px-10"
              >
                Loading jobs and applications…
              </p>
            )}

            <div className="space-y-8 p-5 pb-24 sm:p-8 sm:pb-24 lg:p-10">
              {/* ============================ Dashboard ============================ */}
              {activePage === "Dashboard" && (
                <>
                  <BackendAuthCheck />

                  <section className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
                    {stats.map(
                      ({ label, value, delta, icon: Icon, style, page }) => (
                        <button
                          key={label}
                          type="button"
                          onClick={() => goTo(page)}
                          className="stat-card min-w-0 rounded-2xl border border-slate-200/80 bg-white p-4 text-left transition hover:border-violet-200 sm:p-6"
                        >
                          <div className="flex items-center justify-between">
                            <div
                              className={`flex h-10 w-10 items-center justify-center rounded-xl sm:h-11 sm:w-11 ${style}`}
                            >
                              <Icon size={22} weight="duotone" />
                            </div>
                            <ArrowUpRight
                              size={18}
                              className="text-slate-300"
                            />
                          </div>
                          <p className="mt-4 text-xl font-extrabold tracking-tight text-slate-900 sm:mt-5 sm:text-2xl">
                            {value}
                          </p>
                          <p className="mt-1 truncate text-sm font-semibold text-slate-600">
                            {label}
                          </p>
                          <p className="mt-2 truncate text-xs text-slate-400">
                            {delta}
                          </p>
                        </button>
                      ),
                    )}
                  </section>

                  <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
                    <div className="space-y-6 xl:col-span-2">
                      {/* Next steps */}
                      <article className="rounded-2xl border border-slate-200/80 bg-white p-5 sm:p-6">
                        <h2 className="text-lg font-extrabold text-slate-900">
                          Your next steps
                        </h2>
                        <p className="mt-1 text-sm text-slate-500">
                          Follow these in order, or jump to whichever applies.
                        </p>

                        <ol className="mt-5 space-y-3">
                          {nextSteps.map((step, index) => (
                            <li
                              key={step.title}
                              className="flex items-start gap-3 rounded-xl border border-slate-100 p-3 sm:items-center sm:p-4"
                            >
                              {step.done ? (
                                <CheckCircle
                                  size={26}
                                  weight="fill"
                                  className="shrink-0 text-emerald-500"
                                  aria-label="Done"
                                />
                              ) : (
                                <span className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-bold text-slate-500">
                                  {index + 1}
                                </span>
                              )}
                              <div className="min-w-0 flex-1">
                                <p
                                  className={`text-sm font-semibold ${
                                    step.done
                                      ? "text-slate-400 line-through"
                                      : "text-slate-800"
                                  }`}
                                >
                                  {step.title}
                                </p>
                                <p className="mt-0.5 text-xs text-slate-500">
                                  {step.description}
                                </p>
                              </div>
                              <button
                                type="button"
                                onClick={() => goTo(step.page)}
                                className="shrink-0 rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-violet-700 hover:bg-violet-50"
                              >
                                {step.cta}
                              </button>
                            </li>
                          ))}
                        </ol>
                      </article>

                      {/* Recent applications */}
                      <article className="rounded-2xl border border-slate-200/80 bg-white p-5 sm:p-6">
                        <div className="flex items-center justify-between gap-3">
                          <h2 className="text-lg font-extrabold text-slate-900">
                            Recent applications
                          </h2>
                          {applications.length > 0 && (
                            <button
                              type="button"
                              onClick={() => goTo("Applications")}
                              className="flex items-center gap-1 text-sm font-bold text-violet-600 hover:text-violet-800"
                            >
                              View all <CaretRight size={16} />
                            </button>
                          )}
                        </div>

                        {applications.length === 0 ? (
                          <p className="mt-3 text-sm text-slate-500">
                            Nothing tracked yet. Save a job from{" "}
                            <button
                              type="button"
                              onClick={() => goTo("Find Jobs")}
                              className="font-semibold text-violet-700 underline underline-offset-2"
                            >
                              Find jobs
                            </button>{" "}
                            and it will appear here.
                          </p>
                        ) : recentApplications.length === 0 ? (
                          <p className="mt-3 text-sm text-slate-500">
                            Loading your applications…
                          </p>
                        ) : (
                          <ul className="mt-4 divide-y divide-slate-100">
                            {recentApplications.map((job) => (
                              <li
                                key={job.id}
                                className="flex items-center gap-3 py-3"
                              >
                                <div
                                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-extrabold ${job.color}`}
                                >
                                  {job.letter}
                                </div>
                                <div className="min-w-0 flex-1">
                                  <p className="truncate text-sm font-semibold text-slate-800">
                                    {job.title}
                                  </p>
                                  <p className="truncate text-xs text-slate-500">
                                    {job.company}
                                  </p>
                                </div>
                                <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold text-slate-600">
                                  {job.status}
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </article>
                    </div>

                    {/* Weekly activity */}
                    <article className="flex flex-col rounded-2xl bg-[#111426] p-5 text-white sm:p-6">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-semibold text-slate-300">
                            Weekly activity
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            Applications created in the last 7 days
                          </p>
                        </div>
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/15 text-violet-300">
                          <TrendUp size={21} />
                        </div>
                      </div>

                      <div className="mt-8 flex h-36 items-end gap-2 sm:gap-3">
                        {activity.map(({ day, count, height }) => (
                          <div
                            key={day}
                            className="flex h-full flex-1 flex-col items-center justify-end gap-3"
                          >
                            <div
                              title={`${day}: ${count} application(s)`}
                              className={`w-full rounded-t-md transition-all hover:opacity-70 ${
                                count > 0
                                  ? "bg-gradient-to-t from-violet-700 to-fuchsia-400"
                                  : "bg-slate-700"
                              }`}
                              style={{ height: `${height}%` }}
                            />
                            <span className="text-[10px] text-slate-500">
                              {day}
                            </span>
                          </div>
                        ))}
                      </div>

                      <div className="mt-7 border-t border-white/10 pt-5">
                        <p className="text-xs text-slate-400">
                          Applications tracked
                        </p>
                        <p className="mt-2 text-2xl font-extrabold">
                          {applications.length}
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={() => goTo("Insights")}
                        className="mt-6 flex items-center justify-center gap-2 rounded-xl border border-white/10 py-3 text-sm font-semibold text-slate-200 transition hover:bg-white/5"
                      >
                        View insights <ArrowUpRight size={17} />
                      </button>
                    </article>
                  </section>
                </>
              )}

              {/* ============================ Find Jobs ============================ */}
              {activePage === "Find Jobs" && (
                <section className="space-y-4">
                  <div className="grid grid-cols-1 gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-2 xl:grid-cols-6">
                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold text-slate-600">
                        Work arrangement
                      </span>
                      <select
                        value={remoteType}
                        onChange={(event) =>
                          updateJobFilter(() => setRemoteType(event.target.value))
                        }
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"
                      >
                        <option value="">All arrangements</option>
                        <option value="remote">Remote</option>
                        <option value="hybrid">Hybrid</option>
                        <option value="onsite">On-site</option>
                        <option value="unknown">Unknown</option>
                      </select>
                    </label>

                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold text-slate-600">
                        Employment type
                      </span>
                      <select
                        value={employmentType}
                        onChange={(event) =>
                          updateJobFilter(() =>
                            setEmploymentType(event.target.value),
                          )
                        }
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"
                      >
                        <option value="">All employment types</option>
                        <option value="full-time">Full-time</option>
                        <option value="part-time">Part-time</option>
                        <option value="contract">Contract</option>
                        <option value="internship">Internship</option>
                        <option value="unknown">Unknown</option>
                      </select>
                    </label>

                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold text-slate-600">
                        Experience level
                      </span>
                      <select
                        value={experienceLevel}
                        onChange={(event) =>
                          updateJobFilter(() =>
                            setExperienceLevel(event.target.value),
                          )
                        }
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"
                      >
                        <option value="">All experience levels</option>
                        <option value="entry-level">Entry-level</option>
                        <option value="junior">Junior</option>
                        <option value="mid-level">Mid-level</option>
                        <option value="senior">Senior</option>
                        <option value="internship">Internship</option>
                        <option value="unknown">Unknown</option>
                      </select>
                    </label>

                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold text-slate-600">
                        Kenya eligibility
                      </span>
                      <select
                        value={eligibilityStatus}
                        onChange={(event) =>
                          updateJobFilter(() =>
                            setEligibilityStatus(event.target.value),
                          )
                        }
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"
                      >
                        <option value="">All eligibility statuses</option>
                        <option value="eligible">Eligible</option>
                        <option value="ineligible">Ineligible</option>
                        <option value="unknown">Unverified</option>
                      </select>
                    </label>

                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold text-slate-600">
                        Listing status
                      </span>
                      <select
                        value={listingStatus}
                        onChange={(event) =>
                          updateJobFilter(() =>
                            setListingStatus(event.target.value),
                          )
                        }
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"
                      >
                        <option value="">All listing statuses</option>
                        <option value="active">Active</option>
                        <option value="closed">Closed</option>
                        <option value="unknown">Unverified</option>
                      </select>
                    </label>

                    <label className="space-y-1.5">
                      <span className="text-xs font-semibold text-slate-600">
                        Sort by
                      </span>
                      <select
                        value={sortBy}
                        onChange={(event) =>
                          updateJobFilter(() =>
                            setSortBy(event.target.value as "newest" | "relevance"),
                          )
                        }
                        className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"
                      >
                        <option value="newest">Newest first</option>
                        <option value="relevance">Most relevant</option>
                      </select>
                    </label>

                    {hasActiveFilters && (
                      <button
                        type="button"
                        onClick={clearJobFilters}
                        className="text-left text-sm font-semibold text-violet-600 hover:text-violet-800 sm:col-span-2 xl:col-span-6"
                      >
                        Clear all filters
                      </button>
                    )}
                  </div>

                  <div className="space-y-3">
                    {jobsLoading && jobCards.length === 0 && (
                      <p className="py-6 text-center text-sm text-slate-500">
                        Searching jobs…
                      </p>
                    )}

                    {!jobsLoading && jobCards.length === 0 && (
                      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
                        <MagnifyingGlass
                          size={28}
                          className="mx-auto text-slate-400"
                        />
                        <p className="mt-3 font-semibold text-slate-800">
                          No matching jobs
                        </p>
                        <p className="mt-1 text-sm text-slate-500">
                          {hasActiveFilters
                            ? "Try a different title or company, or clear your filters."
                            : "No jobs have been added yet. Check back soon."}
                        </p>
                        {hasActiveFilters && (
                          <button
                            type="button"
                            onClick={clearJobFilters}
                            className="mt-4 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700"
                          >
                            Clear filters
                          </button>
                        )}
                      </div>
                    )}

                    {jobCards.map(({ job, apiJob }) => (
                      <JobCard
                        key={job.id}
                        job={job}
                        apiJob={apiJob}
                        application={applicationByJobId.get(job.id)}
                        saving={savingJobId === job.id}
                        isAdmin={isAdmin}
                        onSave={() => void saveJob(job.id)}
                        onMarkApplied={(id) => void changeStatus(id, "applied")}
                        onEligibilityUpdated={handleEligibilityUpdated}
                      />
                    ))}
                  </div>

                  <div className="flex flex-col gap-3 border-t border-slate-200 pt-4 sm:flex-row sm:items-center sm:justify-between">
                    <p className="text-sm text-slate-500" aria-live="polite">
                      {jobsLoading
                        ? "Searching jobs…"
                        : jobTotal === 0
                          ? "No jobs found"
                          : `Showing ${firstResult}–${lastResult} of ${jobTotal} jobs`}
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setJobPage((page) => Math.max(1, page - 1))}
                        disabled={jobsLoading || jobPage <= 1}
                        className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Previous
                      </button>
                      <span className="min-w-24 text-center text-sm text-slate-600">
                        Page {Math.min(jobPage, totalPages)} of {totalPages}
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          setJobPage((page) => Math.min(totalPages, page + 1))
                        }
                        disabled={jobsLoading || jobPage >= totalPages}
                        className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                </section>
              )}

              {/* =========================== Resume Match =========================== */}
              {activePage === "Resume Match" && (
                <section className="space-y-5 rounded-2xl border border-violet-100 bg-white p-5 sm:p-6">
                  <p className="max-w-2xl text-sm leading-6 text-slate-600">
                    Scores measure text overlap between your resume and stored
                    job descriptions, not your probability of being hired.
                    Eligibility and listing status are assessed separately.
                  </p>

                  <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                    <label className="min-w-0 flex-1 space-y-1.5">
                      <span className="text-sm font-semibold text-slate-700">
                        Resume
                      </span>
                      <select
                        value={selectedResumeId}
                        onChange={(event) => {
                          setSelectedResumeId(event.target.value);
                          setResumeMatches(null);
                          setResumeMatchError("");
                          setResumeMatchNotice("");
                        }}
                        disabled={resumesLoading || resumes.length === 0}
                        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm"
                      >
                        <option value="">
                          {resumesLoading
                            ? "Loading resumes..."
                            : resumes.length === 0
                              ? "No resumes uploaded"
                              : "Choose a resume"}
                        </option>
                        {resumes.map((resume) => (
                          <option key={resume.id} value={String(resume.id)}>
                            {resume.original_filename}
                          </option>
                        ))}
                      </select>
                    </label>

                    <button
                      type="button"
                      onClick={() => void matchJobsToResume()}
                      disabled={
                        !selectedResumeId || matchingLoading || resumesLoading
                      }
                      className="rounded-xl bg-violet-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {matchingLoading ? "Matching jobs..." : "Match my resume"}
                    </button>

                    <button
                      type="button"
                      onClick={() => void loadResumes()}
                      disabled={resumesLoading}
                      className="rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                    >
                      Refresh resumes
                    </button>
                  </div>

                  {!resumesLoading && resumes.length === 0 && (
                    <p className="text-sm text-slate-600">
                      Upload a PDF or DOCX resume first.
                      <button
                        type="button"
                        onClick={() => goTo("My Documents")}
                        className="ml-1 font-semibold text-violet-700 underline underline-offset-2"
                      >
                        Open My Documents
                      </button>
                    </p>
                  )}

                  {resumeMatchError && (
                    <p
                      role="alert"
                      className="rounded-xl bg-rose-50 p-3 text-sm text-rose-700"
                    >
                      {resumeMatchError}
                    </p>
                  )}

                  {resumeMatchNotice && (
                    <p role="status" className="text-sm text-slate-600">
                      {resumeMatchNotice}
                    </p>
                  )}

                  {resumeMatches && (
                    <div className="space-y-4">
                      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-4">
                        <h3 className="font-bold text-slate-900">
                          Resume match results
                        </h3>
                        <span className="text-sm text-slate-500">
                          {resumeMatches.total} jobs analysed
                        </span>
                      </div>

                      {resumeMatches.items.length === 0 && (
                        <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                          No stored jobs were available to compare with this
                          resume.
                        </p>
                      )}

                      {resumeMatches.items.map((match) => (
                        <ResumeMatchCard
                          key={match.id}
                          match={match}
                          application={applicationByJobId.get(match.id)}
                          saving={savingJobId === match.id}
                          onSave={() => void saveJob(match.id)}
                          onMarkApplied={(id) => void changeStatus(id, "applied")}
                        />
                      ))}
                    </div>
                  )}
                </section>
              )}

              {/* ============================ My Documents ========================== */}
              {activePage === "My Documents" && (
                <MyDocuments onOpenEditor={openDraftEditor} />
              )}

              {/* ======================== Reusable Answers ======================== */}
              {activePage === "Reusable Answers" && <ReusableAnswers />}

              {/* ======================== Cover Letter Drafts ======================== */}
              {activePage === "Cover Letter Drafts" && (
                <CoverLetterDrafts initialDraftId={draftToOpenId} />
              )}

              {/* ============================ Applications ========================== */}
              {activePage === "Applications" && (
                <section className="space-y-4 pb-5">
                  <div className="flex flex-wrap items-end justify-between gap-4">
                    <div>
                      <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900">
                        <Briefcase size={21} className="text-violet-600" />
                        Application pipeline
                      </h2>
                      <p className="mt-1 text-sm text-slate-500">
                        Use the status menu on any job to move it forward.
                      </p>
                    </div>

                    <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-1">
                      <button
                        type="button"
                        onClick={() => setView("board")}
                        aria-pressed={view === "board"}
                        className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold ${
                          view === "board"
                            ? "bg-slate-100 text-slate-900"
                            : "text-slate-500 hover:text-slate-900"
                        }`}
                      >
                        <Kanban size={16} /> Board
                      </button>
                      <button
                        type="button"
                        onClick={() => setView("list")}
                        aria-pressed={view === "list"}
                        className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold ${
                          view === "list"
                            ? "bg-slate-100 text-slate-900"
                            : "text-slate-500 hover:text-slate-900"
                        }`}
                      >
                        <List size={16} /> List
                      </button>
                    </div>
                  </div>

                  {applications.length === 0 ? (
                    <EmptyState
                      title="No applications yet"
                      description="Save a job from Find jobs and it will show up here, ready to move through your pipeline."
                      actionLabel="Find jobs"
                      onAction={() => goTo("Find Jobs")}
                    />
                  ) : trackedStillLoading ? (
                    <p className="py-6 text-center text-sm text-slate-500">
                      Loading your applications…
                    </p>
                  ) : view === "board" ? (
                    <div className="custom-scrollbar -mx-5 flex snap-x snap-mandatory gap-4 overflow-x-auto px-5 pb-4 sm:mx-0 sm:snap-none sm:px-0">
                      {pipelineColumns.map((column) => {
                        const columnJobs = trackedJobs.filter(
                          (job) => job.status === column.name,
                        );

                        return (
                          <div
                            key={column.name}
                            className="kanban-column w-[80%] shrink-0 snap-start space-y-3 sm:w-64 sm:flex-1"
                          >
                            <div className="flex items-center justify-between px-1 py-2">
                              <div className="flex items-center gap-2">
                                <span
                                  className={`h-2 w-2 rounded-full ${column.dot}`}
                                />
                                <span
                                  className={`text-xs font-bold ${column.color}`}
                                >
                                  {column.name}
                                </span>
                                <span className="rounded-md bg-slate-200/70 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
                                  {columnJobs.length}
                                </span>
                              </div>
                            </div>

                            {columnJobs.length === 0 ? (
                              <div className="rounded-2xl border border-dashed border-slate-200 bg-white/60 p-5 text-center text-xs text-slate-400">
                                Nothing here yet
                              </div>
                            ) : (
                              columnJobs.map((job) => (
                                <article
                                  key={job.id}
                                  className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm"
                                >
                                  <div className="flex items-start gap-3">
                                    <div
                                      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sm font-extrabold ${job.color}`}
                                    >
                                      {job.letter}
                                    </div>
                                    <div className="min-w-0">
                                      <h3 className="text-sm font-bold text-slate-800">
                                        {job.title}
                                      </h3>
                                      <p className="mt-1 text-xs text-slate-500">
                                        {job.company}
                                      </p>
                                    </div>
                                  </div>
                                  <div className="mt-4 flex items-center justify-between gap-3 border-t border-slate-100 pt-3">
                                    <span className="min-w-0 truncate text-[10px] text-slate-400">
                                      {job.location}
                                    </span>
                                    <select
                                      aria-label={`Change status for ${job.title}`}
                                      value={job.apiStatus ?? "saved"}
                                      onChange={(event) => {
                                        if (job.applicationId !== null) {
                                          void changeStatus(
                                            job.applicationId,
                                            event.target.value as ApiApplication["status"],
                                          );
                                        }
                                      }}
                                      className="max-w-32 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-semibold text-violet-700"
                                    >
                                      <option value="saved">Saved</option>
                                      <option value="applied">Applied</option>
                                      <option value="interview">Interview</option>
                                      <option value="offer">Offer</option>
                                      <option value="rejected">Rejected</option>
                                    </select>
                                  </div>
                                  {job.sourceUrl && (
                                    <a
                                      href={job.sourceUrl}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="mt-3 inline-block text-xs font-semibold text-violet-700 underline underline-offset-2"
                                    >
                                      View listing
                                    </a>
                                  )}
                                </article>
                              ))
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
                      <table className="w-full min-w-[460px] text-left text-sm sm:min-w-[620px]">
                        <thead className="bg-slate-50 text-xs text-slate-500">
                          <tr>
                            <th className="px-4 py-4 font-semibold sm:px-5">
                              Position
                            </th>
                            <th className="hidden px-5 py-4 font-semibold sm:table-cell">
                              Location
                            </th>
                            <th className="px-4 py-4 font-semibold sm:px-5">
                              Status
                            </th>
                            <th className="px-4 py-4 font-semibold sm:px-5">
                              Change status
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {trackedJobs.map((job) => (
                            <tr key={job.id}>
                              <td className="px-4 py-4 sm:px-5">
                                <p className="font-semibold text-slate-800">
                                  {job.title}
                                </p>
                                <p className="mt-1 text-xs text-slate-500">
                                  {job.company}
                                </p>
                                {job.sourceUrl && (
                                  <a
                                    href={job.sourceUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="mt-1 inline-block text-xs font-semibold text-violet-700 underline underline-offset-2"
                                  >
                                    View listing
                                  </a>
                                )}
                              </td>
                              <td className="hidden px-5 py-4 text-slate-600 sm:table-cell">
                                {job.location}
                              </td>
                              <td className="px-4 py-4 text-slate-600 sm:px-5">
                                {job.status}
                              </td>
                              <td className="px-4 py-4 sm:px-5">
                                <select
                                  aria-label={`Change status for ${job.title}`}
                                  value={job.apiStatus ?? "saved"}
                                  onChange={(event) => {
                                    if (job.applicationId !== null) {
                                      void changeStatus(
                                        job.applicationId,
                                        event.target.value as ApiApplication["status"],
                                      );
                                    }
                                  }}
                                  className="max-w-32 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs font-semibold text-violet-700"
                                >
                                  <option value="saved">Saved</option>
                                  <option value="applied">Applied</option>
                                  <option value="interview">Interview</option>
                                  <option value="offer">Offer</option>
                                  <option value="rejected">Rejected</option>
                                </select>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              )}

              {/* ====================== Batches / Executions / Insights ====================== */}
              {activePage === "Application Batches" && <ApplicationBatches />}
              {activePage === "Application Executions" && (
                <ApplicationExecutions />
              )}
              {activePage === "Insights" && <Insights />}

              {/* ============================ Admin Tools =========================== */}
              {activePage === "Admin Tools" && isAdmin && (
                <div className="space-y-6">
                  <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
                    <h2 className="text-lg font-bold text-slate-900">
                      Import job listings
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                      Pull the latest listings from external sources. New jobs
                      appear in Find jobs when the import finishes.
                    </p>

                    <div className="mt-5 flex flex-wrap gap-3">
                      <button
                        type="button"
                        onClick={importJobicy}
                        disabled={isImportingJobicy || isImportingHimalayas}
                        className="rounded-xl border border-emerald-200 bg-white px-4 py-2.5 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {isImportingJobicy
                          ? "Importing Jobicy jobs..."
                          : "Import Jobicy jobs"}
                      </button>

                      <button
                        type="button"
                        onClick={importHimalayas}
                        disabled={isImportingHimalayas || isImportingJobicy}
                        className="rounded-xl border border-sky-200 bg-white px-4 py-2.5 text-sm font-semibold text-sky-700 transition hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {isImportingHimalayas
                          ? "Importing Himalayas jobs..."
                          : "Import Himalayas jobs"}
                      </button>
                    </div>
                  </section>

                  <section className="rounded-2xl border border-violet-200 bg-white p-5 shadow-sm sm:p-7">
                    <div className="mb-5">
                      <h2 className="text-lg font-bold text-slate-900">
                        Add a job listing
                      </h2>
                      <p className="mt-1 text-sm text-slate-500">
                        Add an opportunity for users to discover and track.
                      </p>
                    </div>

                    <form onSubmit={createJob} className="space-y-4">
                      <div className="grid gap-4 sm:grid-cols-2">
                        <label className="block text-sm font-medium text-slate-700">
                          Job title *
                          <input
                            required
                            maxLength={255}
                            value={jobForm.title}
                            onChange={(event) =>
                              setJobForm((current) => ({
                                ...current,
                                title: event.target.value,
                              }))
                            }
                            className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                            placeholder="e.g. Junior Backend Developer"
                          />
                        </label>

                        <label className="block text-sm font-medium text-slate-700">
                          Company *
                          <input
                            required
                            maxLength={255}
                            value={jobForm.company}
                            onChange={(event) =>
                              setJobForm((current) => ({
                                ...current,
                                company: event.target.value,
                              }))
                            }
                            className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                            placeholder="Company name"
                          />
                        </label>

                        <label className="block text-sm font-medium text-slate-700">
                          Location
                          <input
                            maxLength={255}
                            value={jobForm.location}
                            onChange={(event) =>
                              setJobForm((current) => ({
                                ...current,
                                location: event.target.value,
                              }))
                            }
                            className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                            placeholder="e.g. Remote or Nairobi, Kenya"
                          />
                        </label>

                        <label className="block text-sm font-medium text-slate-700">
                          Employment type
                          <select
                            value={jobForm.employment_type}
                            onChange={(event) =>
                              setJobForm((current) => ({
                                ...current,
                                employment_type: event.target.value,
                              }))
                            }
                            className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                          >
                            <option value="">Not specified</option>
                            <option value="Full-time">Full-time</option>
                            <option value="Part-time">Part-time</option>
                            <option value="Contract">Contract</option>
                            <option value="Internship">Internship</option>
                            <option value="Temporary">Temporary</option>
                          </select>
                        </label>

                        <label className="block text-sm font-medium text-slate-700 sm:col-span-2">
                          Job URL
                          <input
                            type="url"
                            maxLength={2048}
                            value={jobForm.source_url}
                            onChange={(event) =>
                              setJobForm((current) => ({
                                ...current,
                                source_url: event.target.value,
                              }))
                            }
                            className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                            placeholder="https://company.com/careers/job"
                          />
                        </label>

                        <label className="block text-sm font-medium text-slate-700 sm:col-span-2">
                          Description
                          <textarea
                            rows={5}
                            value={jobForm.description}
                            onChange={(event) =>
                              setJobForm((current) => ({
                                ...current,
                                description: event.target.value,
                              }))
                            }
                            className="mt-1.5 w-full resize-y rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                            placeholder="Responsibilities, requirements, qualifications, and application instructions..."
                          />
                        </label>
                      </div>

                      {jobFormError && (
                        <p
                          role="alert"
                          className="rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700"
                        >
                          {jobFormError}
                        </p>
                      )}

                      <div className="flex flex-wrap justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => {
                            setJobForm(emptyJobForm);
                            setJobFormError("");
                          }}
                          disabled={creatingJob}
                          className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                        >
                          Reset
                        </button>
                        <button
                          type="submit"
                          disabled={creatingJob}
                          className="rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {creatingJob ? "Creating job..." : "Create job"}
                        </button>
                      </div>
                    </form>
                  </section>
                </div>
              )}

              <footer className="border-t border-slate-200 py-5 text-xs text-slate-400">
                AI Applier · Your job search, organized. Jobs and application
                statuses are loaded from your backend.
              </footer>
            </div>
          </main>
        </div>

        {/* ----------------------- Mobile "More" menu ----------------------- */}
        {mobileMoreOpen && (
          <div className="fixed inset-x-3 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-40 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl lg:hidden">
            {mobileMoreItems.map(({ page, icon: Icon }) => (
              <button
                key={page}
                type="button"
                onClick={() => goTo(page)}
                className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium ${
                  activePage === page
                    ? "bg-violet-50 text-violet-700"
                    : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                <Icon size={20} />
                {page}
              </button>
            ))}
          </div>
        )}

        {/* ----------------------- Mobile bottom navigation ----------------------- */}
        <nav
          aria-label="Mobile dashboard navigation"
          className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
        >
          {mobileBarItems.map(({ label, page, icon: Icon }) => {
            const active = activePage === page;

            return (
              <button
                key={page}
                type="button"
                onClick={() => goTo(page)}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-14 min-w-0 flex-col items-center justify-center gap-1 px-0.5 text-[10px] font-semibold ${
                  active ? "text-violet-600" : "text-slate-500"
                }`}
              >
                <Icon size={22} weight={active ? "fill" : "duotone"} />
                <span className="whitespace-nowrap">{label}</span>
              </button>
            );
          })}

          {(() => {
            const moreActive =
              mobileMoreOpen ||
              mobileMoreItems.some((item) => item.page === activePage);

            return (
              <button
                type="button"
                onClick={() => setMobileMoreOpen((open) => !open)}
                aria-expanded={mobileMoreOpen}
                className={`flex min-h-14 min-w-0 flex-col items-center justify-center gap-1 px-0.5 text-[10px] font-semibold ${
                  moreActive ? "text-violet-600" : "text-slate-500"
                }`}
              >
                <List size={22} weight={moreActive ? "fill" : "duotone"} />
                <span className="whitespace-nowrap">More</span>
              </button>
            );
          })()}
        </nav>
      </div>
    </>
  );
}
