"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { useAuth } from "@clerk/nextjs";

/* -------------------------------------------------------------------------- */
/*  Types                                                                     */
/* -------------------------------------------------------------------------- */

type Application = {
  id: number;
  job_id: number;
  status: "saved" | "applied" | "interview" | "rejected" | "offer";
};

type Resume = {
  id: number;
  original_filename: string;
};

type CoverLetterDraft = {
  id: number;
  application_id: number;
  content: string;
  updated_at: string;
};

type ExecutionStatus =
  | "prepared"
  | "approved"
  | "submitting"
  | "submitted"
  | "failed"
  | "needs_attention";

type ExtensionHandoff = {
  token: string;
  expires_at: string;
};

type ApplicationExecution = {
  id: number;
  application_id: number;
  resume_id: number | null;
  cover_letter_draft_id: number | null;
  resume_filename_snapshot: string | null;
  resume_sha256: string | null;
  cover_letter_snapshot: string | null;
  job_snapshot: Record<string, unknown>;
  application_payload: Record<string, unknown>;
  target_url: string;
  ats_platform: string;
  status: ExecutionStatus;
  reviewed_at: string | null;
  approved_at: string | null;
  submitted_at: string | null;
  submission_reference: string | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
};

type JobSummary = { title: string; company: string };

type NavTarget =
  | "My Documents"
  | "Cover Letter Drafts"
  | "Find Jobs"
  | "Applications";

type Props = {
  /** Optional: lets the empty-state hints link to other dashboard pages. */
  onNavigate?: (page: NavTarget) => void;
};

type Filter = "all" | "todo" | "submitted" | "issues";

/* -------------------------------------------------------------------------- */
/*  Helpers                                                                   */
/* -------------------------------------------------------------------------- */

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

function snapshotText(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Not provided";
  }

  if (Array.isArray(value)) {
    return value.map((item) => snapshotText(item)).join(", ");
  }

  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }

  return String(value);
}

function formatPlatform(platform: string): string {
  if (platform === "unsupported") return "Not supported";
  return platform.charAt(0).toUpperCase() + platform.slice(1).replace(/_/g, " ");
}

const STEP_LABELS = ["Prepared", "Reviewed", "Approved", "Submitted"] as const;

/** How far an execution has progressed through the four steps. */
function getProgress(execution: ApplicationExecution): {
  done: number;
  problem: boolean;
} {
  switch (execution.status) {
    case "submitted":
      return { done: 4, problem: false };
    case "approved":
    case "submitting":
      return { done: 3, problem: false };
    case "failed":
    case "needs_attention":
      return {
        done: execution.approved_at ? 3 : execution.reviewed_at ? 2 : 1,
        problem: true,
      };
    default:
      return { done: execution.reviewed_at ? 2 : 1, problem: false };
  }
}

/** Plain-language label for what state the execution is really in. */
function getStage(execution: ApplicationExecution): {
  label: string;
  style: string;
} {
  switch (execution.status) {
    case "prepared":
      return execution.reviewed_at
        ? { label: "Ready to approve", style: "bg-violet-100 text-violet-700" }
        : { label: "Needs review", style: "bg-amber-100 text-amber-700" };
    case "approved":
      return { label: "Approved", style: "bg-indigo-100 text-indigo-700" };
    case "submitting":
      return { label: "Submitting", style: "bg-amber-100 text-amber-700" };
    case "submitted":
      return { label: "Submitted", style: "bg-emerald-100 text-emerald-700" };
    case "failed":
      return { label: "Failed", style: "bg-red-100 text-red-700" };
    case "needs_attention":
      return {
        label: "Needs attention",
        style: "bg-orange-100 text-orange-700",
      };
  }
}

function filterOf(execution: ApplicationExecution): Exclude<Filter, "all"> {
  if (execution.status === "submitted") return "submitted";
  if (execution.status === "failed" || execution.status === "needs_attention") {
    return "issues";
  }
  return "todo";
}

/* -------------------------------------------------------------------------- */
/*  Step tracker                                                              */
/* -------------------------------------------------------------------------- */

function StepTracker({ execution }: { execution: ApplicationExecution }) {
  const { done, problem } = getProgress(execution);

  return (
    <ol
      aria-label="Progress"
      className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-2"
    >
      {STEP_LABELS.map((label, index) => {
        const complete = index < done;
        const current = index === done;
        const bad = current && problem;

        return (
          <li key={label} className="flex items-center gap-2">
            {index > 0 && (
              <span
                aria-hidden="true"
                className={`h-px w-5 ${complete ? "bg-emerald-300" : "bg-slate-200"}`}
              />
            )}
            <span
              className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                complete
                  ? "bg-emerald-500 text-white"
                  : bad
                    ? "bg-red-500 text-white"
                    : current
                      ? "bg-violet-600 text-white"
                      : "bg-slate-100 text-slate-400"
              }`}
            >
              {complete ? "✓" : bad ? "!" : index + 1}
            </span>
            <span
              className={`text-xs font-semibold ${
                complete
                  ? "text-emerald-700"
                  : bad
                    ? "text-red-600"
                    : current
                      ? "text-violet-700"
                      : "text-slate-400"
              }`}
            >
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

/* -------------------------------------------------------------------------- */
/*  Execution card                                                            */
/* -------------------------------------------------------------------------- */

function ExecutionCard({
  execution,
  expanded,
  busy,
  confirmingApproval,
  handoff,
  handoffLoading,
  onToggleSnapshot,
  onReview,
  onAskApproval,
  onConfirmApproval,
  onCancelApproval,
  onGenerateHandoff,
  onCopyToken,
  onHideToken,
}: {
  execution: ApplicationExecution;
  expanded: boolean;
  busy: boolean;
  confirmingApproval: boolean;
  handoff: (ExtensionHandoff & { executionId: number }) | null;
  handoffLoading: boolean;
  onToggleSnapshot: () => void;
  onReview: () => void;
  onAskApproval: () => void;
  onConfirmApproval: () => void;
  onCancelApproval: () => void;
  onGenerateHandoff: () => void;
  onCopyToken: () => void;
  onHideToken: () => void;
}) {
  const job = execution.job_snapshot;
  const stage = getStage(execution);

  const needsReview = execution.status === "prepared" && !execution.reviewed_at;
  const readyToApprove =
    execution.status === "prepared" && Boolean(execution.reviewed_at);
  const approvedGreenhouse =
    execution.status === "approved" && execution.ats_platform === "greenhouse";
  const approvedManual =
    execution.status === "approved" && execution.ats_platform !== "greenhouse";

  const primaryBtn =
    "rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50";
  const secondaryBtn =
    "rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50";

  // One sentence telling the person exactly what to do next.
  let nextStep: string;
  if (needsReview) {
    nextStep =
      "Next: check the job, resume and cover letter in the snapshot, then mark it as reviewed.";
  } else if (readyToApprove) {
    nextStep =
      "Next: approve the snapshot. Approving does not submit anything to the employer.";
  } else if (approvedGreenhouse) {
    nextStep =
      "Next: generate a one-time token and paste it into the AI Applier Chrome extension to continue on the employer's site.";
  } else if (approvedManual) {
    nextStep = `Automatic submission is not available for this platform (${formatPlatform(execution.ats_platform)}). Open the application page and apply yourself.`;
  } else if (execution.status === "submitting") {
    nextStep = "Submission is in progress. Use Refresh to see the latest status.";
  } else if (execution.status === "submitted") {
    nextStep = execution.submission_reference
      ? `Submitted. Reference: ${execution.submission_reference}`
      : "Submitted.";
  } else {
    nextStep = execution.failure_reason || "Something went wrong with this application.";
  }

  return (
    <article className="rounded-xl border border-slate-200 p-4 sm:p-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-bold text-slate-900">
            {snapshotText(job.title)}
          </h3>
          <p className="mt-1 text-sm font-medium text-slate-600">
            {snapshotText(job.company)}
            <span className="text-slate-400">
              {" "}
              · Prepared {new Date(execution.created_at).toLocaleDateString()} ·
              Execution #{execution.id}
            </span>
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${stage.style}`}
        >
          {stage.label}
        </span>
      </div>

      <StepTracker execution={execution} />

      {/* What to do next */}
      <p
        className={`mt-4 rounded-lg px-3 py-2.5 text-sm leading-6 ${
          execution.status === "failed" || execution.status === "needs_attention"
            ? "bg-red-50 text-red-700"
            : execution.status === "submitted"
              ? "bg-emerald-50 text-emerald-800"
              : "bg-slate-50 text-slate-700"
        }`}
      >
        {nextStep}
      </p>

      {execution.ats_platform === "unsupported" && (
        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-900">
            Unsupported application platform
          </p>
          <p className="mt-1 text-sm leading-6 text-amber-800">
            We have not identified a supported integration for this job. You can
            still review and approve the snapshot, but approval does not enable
            automatic submission.
          </p>
        </div>
      )}

      {/* Actions: one primary action for the current step */}
      <div className="mt-4 flex flex-wrap gap-2">
        {needsReview && !expanded && (
          <button
            type="button"
            onClick={onToggleSnapshot}
            className={primaryBtn}
          >
            Review snapshot
          </button>
        )}

        {needsReview && expanded && (
          <button
            type="button"
            onClick={onReview}
            disabled={busy}
            className={primaryBtn}
          >
            {busy ? "Please wait..." : "Mark as reviewed"}
          </button>
        )}

        {readyToApprove && (
          <button
            type="button"
            onClick={onAskApproval}
            disabled={busy || confirmingApproval}
            className={primaryBtn}
          >
            Approve snapshot
          </button>
        )}

        {approvedGreenhouse && (
          <button
            type="button"
            onClick={onGenerateHandoff}
            disabled={handoffLoading}
            className={primaryBtn}
          >
            {handoffLoading ? "Generating token..." : "Generate extension token"}
          </button>
        )}

        {approvedManual && (
          <a
            href={execution.target_url}
            target="_blank"
            rel="noopener noreferrer"
            className={primaryBtn}
          >
            Open application page
          </a>
        )}

        {!(needsReview && !expanded) && (
          <button
            type="button"
            onClick={onToggleSnapshot}
            aria-expanded={expanded}
            className={secondaryBtn}
          >
            {expanded ? "Hide snapshot" : "View snapshot"}
          </button>
        )}
      </div>

      {/* Approval confirmation */}
      {confirmingApproval && readyToApprove && (
        <div className="mt-4 rounded-xl border border-violet-200 bg-violet-50 p-4">
          <h4 className="text-sm font-bold text-violet-950">
            Approve this snapshot?
          </h4>
          <p className="mt-2 text-sm leading-6 text-violet-900">
            You are approving the saved job, resume and cover letter for
            Execution #{execution.id}. This does not submit an application or
            contact the employer.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onConfirmApproval}
              disabled={busy}
              className={primaryBtn}
            >
              {busy ? "Please wait..." : "Yes, approve"}
            </button>
            <button
              type="button"
              onClick={onCancelApproval}
              disabled={busy}
              className="rounded-lg border border-violet-200 px-4 py-2 text-sm font-semibold text-violet-800 hover:bg-white disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Extension token */}
      {handoff?.executionId === execution.id && (
        <div className="mt-4 rounded-xl border border-violet-200 bg-violet-50 p-4">
          <h4 className="text-sm font-bold text-violet-950">
            One-time extension token
          </h4>
          <p className="mt-1 text-sm text-violet-800">
            Expires {new Date(handoff.expires_at).toLocaleString()}
          </p>
          <code className="mt-3 block overflow-x-auto break-all rounded-lg bg-white p-3 text-sm text-slate-800">
            {handoff.token}
          </code>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={onCopyToken} className={primaryBtn}>
              Copy token
            </button>
            <button
              type="button"
              onClick={onHideToken}
              className="rounded-lg border border-violet-200 px-4 py-2 text-sm font-semibold text-violet-800 hover:bg-white"
            >
              Hide token
            </button>
          </div>
          <p className="mt-3 text-xs leading-5 text-violet-800">
            Paste this token into the AI Applier Chrome extension. It works
            once and is not shown again after you hide it. Do not share it.
          </p>
        </div>
      )}

      {/* Timeline */}
      <div className="mt-4 space-y-1 text-xs">
        {execution.reviewed_at && (
          <p className="text-emerald-700">
            Reviewed {new Date(execution.reviewed_at).toLocaleString()}
          </p>
        )}
        {execution.approved_at && (
          <p className="text-violet-700">
            Approved {new Date(execution.approved_at).toLocaleString()}. This
            does not mean the application was submitted.
          </p>
        )}
        {execution.submitted_at && (
          <p className="text-emerald-700">
            Submitted {new Date(execution.submitted_at).toLocaleString()}
          </p>
        )}
      </div>

      {/* Snapshot */}
      {expanded && (
        <div className="mt-5 space-y-5 rounded-xl border border-slate-200 p-4">
          <section>
            <h4 className="text-sm font-bold text-slate-900">Job</h4>
            <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
              {(
                [
                  ["Title", job.title],
                  ["Company", job.company],
                  ["Location", job.location],
                  ["Employment type", job.employment_type],
                  ["Remote type", job.remote_type],
                  ["Source", job.source_name],
                  ["Eligible countries", job.eligible_countries],
                  ["Eligibility status", job.eligibility_status],
                  ["Application platform", formatPlatform(execution.ats_platform)],
                ] as [string, unknown][]
              ).map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs font-medium text-slate-400">
                    {label}
                  </dt>
                  <dd className="mt-1 break-words text-slate-700">
                    {snapshotText(value)}
                  </dd>
                </div>
              ))}
            </dl>

            <div className="mt-4">
              <p className="text-xs font-medium text-slate-400">
                Application page
              </p>
              <a
                href={execution.target_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 block break-all text-sm font-medium text-violet-700 hover:underline"
              >
                {execution.target_url}
              </a>
            </div>

            <div className="mt-4">
              <h5 className="text-xs font-medium text-slate-400">
                Job description
              </h5>
              <div className="mt-2 max-h-72 overflow-y-auto rounded-lg bg-slate-50 p-3 text-sm leading-6 whitespace-pre-wrap text-slate-700">
                {snapshotText(job.description)}
              </div>
            </div>

            {(job.eligibility_evidence != null ||
              typeof job.eligibility_evidence_url === "string") && (
              <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">
                <p className="font-semibold text-slate-700">
                  Eligibility evidence
                </p>
                {job.eligibility_evidence != null && (
                  <p className="mt-1 whitespace-pre-wrap text-slate-600">
                    {snapshotText(job.eligibility_evidence)}
                  </p>
                )}
                {typeof job.eligibility_evidence_url === "string" && (
                  <a
                    href={job.eligibility_evidence_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 block break-all text-violet-700 hover:underline"
                  >
                    View eligibility evidence
                  </a>
                )}
              </div>
            )}
          </section>

          <section className="border-t border-slate-100 pt-4">
            <h4 className="text-sm font-bold text-slate-900">Resume</h4>
            <p className="mt-2 text-sm break-words text-slate-700">
              {execution.resume_filename_snapshot || "Not available"}
            </p>
            <p className="mt-2 text-xs text-slate-400">SHA-256 fingerprint</p>
            <code className="mt-1 block rounded-lg bg-slate-50 p-3 text-xs break-all text-slate-600">
              {execution.resume_sha256 || "Not available"}
            </code>
            <p className="mt-2 text-xs text-slate-500">
              The fingerprint identifies the resume file captured when this
              application was prepared.
            </p>
          </section>

          <section className="border-t border-slate-100 pt-4">
            <h4 className="text-sm font-bold text-slate-900">Cover letter</h4>
            {execution.cover_letter_snapshot ? (
              <div className="mt-2 max-h-72 overflow-y-auto rounded-lg bg-slate-50 p-3 text-sm leading-6 whitespace-pre-wrap text-slate-700">
                {execution.cover_letter_snapshot}
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-500">
                No cover letter was included.
              </p>
            )}
          </section>

          <section className="border-t border-slate-100 pt-4">
            <h4 className="text-sm font-bold text-slate-900">
              Application data
            </h4>
            <p className="mt-1 text-xs text-slate-500">
              Exactly what was saved for this application. No candidate answers
              have been invented.
            </p>
            <pre className="mt-3 max-h-96 overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-5 break-words whitespace-pre-wrap text-slate-100">
              {JSON.stringify(execution.application_payload, null, 2)}
            </pre>
          </section>
        </div>
      )}
    </article>
  );
}

/* -------------------------------------------------------------------------- */
/*  Main component                                                            */
/* -------------------------------------------------------------------------- */

export default function ApplicationExecutions({ onNavigate }: Props) {
  const { isLoaded, isSignedIn, getToken } = useAuth();

  const [applications, setApplications] = useState<Application[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [drafts, setDrafts] = useState<CoverLetterDraft[]>([]);
  const [executions, setExecutions] = useState<ApplicationExecution[]>([]);
  const [jobsById, setJobsById] = useState<Record<number, JobSummary>>({});
  const jobsCache = useRef<Record<number, JobSummary>>({});

  const [applicationId, setApplicationId] = useState("");
  const [resumeId, setResumeId] = useState("");
  const [draftId, setDraftId] = useState("");

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showForm, setShowForm] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const [actionId, setActionId] = useState<number | null>(null);
  const [confirmApprovalId, setConfirmApprovalId] = useState<number | null>(
    null,
  );
  const [handoff, setHandoff] = useState<
    (ExtensionHandoff & { executionId: number }) | null
  >(null);
  const [handoffLoadingId, setHandoffLoadingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Reuse one idempotency key for identical form input, so a retry or a
  // double-click cannot create duplicate executions.
  const idempotency = useRef<{ signature: string; key: string } | null>(null);

  /* ------------------------------------------------------------------------ */
  /*  Data                                                                    */
  /* ------------------------------------------------------------------------ */

  const loadData = useCallback(async (): Promise<number> => {
    const token = await getToken();

    if (!token) {
      throw new Error("Please sign in again.");
    }

    const [loadedApplications, loadedResumes, loadedDrafts, loadedExecutions] =
      await Promise.all([
        apiRequest<Application[]>("/api/applications?limit=100", token),
        apiRequest<Resume[]>("/api/resumes", token),
        apiRequest<CoverLetterDraft[]>(
          "/api/cover-letter-drafts?limit=100",
          token,
        ),
        apiRequest<ApplicationExecution[]>(
          "/api/application-executions?limit=100",
          token,
        ),
      ]);

    // Look up job titles so people see "Backend Developer · Acme", not "Job #34".
    const missingJobIds = [
      ...new Set(loadedApplications.map((item) => item.job_id)),
    ].filter((id) => !(id in jobsCache.current));

    const lookups = await Promise.allSettled(
      missingJobIds.map((id) =>
        apiRequest<{ id: number; title: string; company: string }>(
          `/api/jobs/${id}`,
          token,
        ),
      ),
    );

    for (const result of lookups) {
      if (result.status === "fulfilled") {
        jobsCache.current[result.value.id] = {
          title: result.value.title,
          company: result.value.company,
        };
      }
    }

    setJobsById({ ...jobsCache.current });
    setApplications(loadedApplications);
    setResumes(loadedResumes);
    setDrafts(loadedDrafts);
    setExecutions(loadedExecutions);

    const selectable = loadedApplications.filter(
      (item) => item.status !== "rejected",
    );

    setApplicationId((current) =>
      current && selectable.some((item) => String(item.id) === current)
        ? current
        : selectable[0]
          ? String(selectable[0].id)
          : "",
    );

    setResumeId((current) =>
      current && loadedResumes.some((item) => String(item.id) === current)
        ? current
        : loadedResumes[0]
          ? String(loadedResumes[0].id)
          : "",
    );

    return loadedExecutions.length;
  }, [getToken]);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");

      try {
        const count = await loadData();
        // First visit with nothing prepared yet: open the form. Otherwise
        // show the list first and keep the form one click away.
        if (!cancelled) setShowForm(count === 0);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load application executions.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();

    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, loadData]);

  /* ------------------------------------------------------------------------ */
  /*  Derived                                                                 */
  /* ------------------------------------------------------------------------ */

  const selectableApplications = useMemo(
    () => applications.filter((item) => item.status !== "rejected"),
    [applications],
  );

  const availableDrafts = useMemo(
    () =>
      drafts.filter((draft) => String(draft.application_id) === applicationId),
    [drafts, applicationId],
  );

  const existingForApplication = useMemo(
    () =>
      executions.filter(
        (item) => String(item.application_id) === applicationId,
      ),
    [executions, applicationId],
  );

  const counts = useMemo(() => {
    const result = { all: executions.length, todo: 0, submitted: 0, issues: 0 };
    for (const item of executions) result[filterOf(item)] += 1;
    return result;
  }, [executions]);

  const visibleExecutions = useMemo(
    () =>
      filter === "all"
        ? executions
        : executions.filter((item) => filterOf(item) === filter),
    [executions, filter],
  );

  function applicationLabel(application: Application): string {
    const job = jobsById[application.job_id];
    const name = job
      ? `${job.title} · ${job.company}`
      : `Job #${application.job_id}`;
    return `${name} (${application.status})`;
  }

  /* ------------------------------------------------------------------------ */
  /*  Actions                                                                 */
  /* ------------------------------------------------------------------------ */

  function clearMessages() {
    setError("");
    setNotice("");
  }

  function toggleSnapshot(executionId: number) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(executionId)) next.delete(executionId);
      else next.add(executionId);
      return next;
    });
  }

  async function refresh() {
    clearMessages();
    setRefreshing(true);

    try {
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed.");
    } finally {
      setRefreshing(false);
    }
  }

  async function prepareExecution(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (saving) return;

    clearMessages();

    if (!applicationId || !resumeId) {
      setError("Choose an application and a resume first.");
      return;
    }

    setSaving(true);

    try {
      const token = await getToken();

      if (!token) throw new Error("Please sign in again.");

      const signature = `${applicationId}:${resumeId}:${draftId}`;
      if (idempotency.current?.signature !== signature) {
        idempotency.current = { signature, key: crypto.randomUUID() };
      }

      const created = await apiRequest<ApplicationExecution>(
        "/api/application-executions/prepare",
        token,
        {
          method: "POST",
          headers: { "Idempotency-Key": idempotency.current.key },
          body: JSON.stringify({
            application_id: Number(applicationId),
            resume_id: Number(resumeId),
            cover_letter_draft_id: draftId ? Number(draftId) : null,
          }),
        },
      );

      idempotency.current = null;

      setExecutions((current) => [
        created,
        ...current.filter((item) => item.id !== created.id),
      ]);

      // Take the person straight to the next step: reviewing the new snapshot.
      setFilter("all");
      setExpandedIds((current) => new Set(current).add(created.id));
      setShowForm(false);
      setDraftId("");
      setNotice(
        "Application prepared. Check the snapshot below, then mark it as reviewed.",
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not prepare this application.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function updateExecution(
    executionId: number,
    action: "review" | "approve",
  ) {
    clearMessages();
    setActionId(executionId);

    try {
      const token = await getToken();

      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApplicationExecution>(
        `/api/application-executions/${executionId}/${action}`,
        token,
        { method: "POST" },
      );

      setExecutions((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );

      if (action === "review") {
        setNotice("Marked as reviewed. You can now approve the snapshot.");
      } else {
        setConfirmApprovalId(null);
        setNotice("Snapshot approved. Nothing has been submitted yet.");
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : `Could not ${action} this application.`,
      );
    } finally {
      setActionId(null);
    }
  }

  async function generateExtensionHandoff(executionId: number) {
    clearMessages();
    setHandoff(null);
    setHandoffLoadingId(executionId);

    try {
      const token = await getToken();

      if (!token) throw new Error("Please sign in again.");

      const issued = await apiRequest<ExtensionHandoff>(
        `/api/application-executions/${executionId}/extension-handoff`,
        token,
        { method: "POST" },
      );

      setHandoff({ ...issued, executionId });
      setNotice("One-time extension token created. Copy it into the extension.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not create an extension token.",
      );
    } finally {
      setHandoffLoadingId(null);
    }
  }

  async function copyToken() {
    if (!handoff) return;

    try {
      await navigator.clipboard.writeText(handoff.token);
      setError("");
      setNotice("Extension token copied to clipboard.");
    } catch {
      setNotice("");
      setError("Could not copy the token. Select it and copy it manually.");
    }
  }

  /* ------------------------------------------------------------------------ */
  /*  Render                                                                  */
  /* ------------------------------------------------------------------------ */

  if (!isLoaded) {
    return <p className="text-sm text-slate-500">Loading authentication...</p>;
  }

  if (!isSignedIn) {
    return (
      <p className="text-sm text-slate-500">
        Sign in to manage application executions.
      </p>
    );
  }

  const filters: { key: Filter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "todo", label: "To do" },
    { key: "submitted", label: "Submitted" },
    { key: "issues", label: "Needs attention" },
  ];

  const linkBtn =
    "font-semibold text-violet-700 underline underline-offset-2 hover:text-violet-900";

  return (
    <div className="space-y-6">
      {/* How it works */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
        <h2 className="text-lg font-bold text-slate-900">
          How preparing an application works
        </h2>
        <ol className="mt-4 grid gap-3 text-sm sm:grid-cols-4">
          {[
            ["1. Prepare", "Pick a saved job, a resume and an optional cover letter."],
            ["2. Review", "Check the saved snapshot and mark it as reviewed."],
            ["3. Approve", "Confirm the snapshot. Nothing is sent yet."],
            ["4. Submit", "Continue on the employer's site with the Chrome extension."],
          ].map(([title, text]) => (
            <li key={title} className="rounded-xl bg-slate-50 p-3">
              <p className="font-semibold text-slate-800">{title}</p>
              <p className="mt-1 text-xs leading-5 text-slate-500">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      {/* Messages */}
      {error && (
        <div
          role="alert"
          className="flex items-start justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          <span className="min-w-0">{error}</span>
          <button
            type="button"
            onClick={() => setError("")}
            aria-label="Dismiss error"
            className="shrink-0 font-bold"
          >
            ×
          </button>
        </div>
      )}

      {notice && (
        <div
          role="status"
          className="flex items-start justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700"
        >
          <span className="min-w-0">{notice}</span>
          <button
            type="button"
            onClick={() => setNotice("")}
            aria-label="Dismiss message"
            className="shrink-0 font-bold"
          >
            ×
          </button>
        </div>
      )}

      {/* Step 1: prepare */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              Prepare an application
            </h2>
            <p className="mt-1 text-sm leading-6 text-slate-500">
              Saves a snapshot of the job, your resume and an optional cover
              letter. Nothing is submitted to an employer.
            </p>
          </div>

          {!loading && (
            <button
              type="button"
              onClick={() => setShowForm((visible) => !visible)}
              aria-expanded={showForm}
              className="rounded-xl border border-violet-200 px-4 py-2 text-sm font-semibold text-violet-700 hover:bg-violet-50"
            >
              {showForm ? "Close" : "Prepare an application"}
            </button>
          )}
        </div>

        {loading && (
          <p className="mt-4 text-sm text-slate-500">Loading your documents...</p>
        )}

        {!loading && showForm && (
          <form onSubmit={prepareExecution} className="mt-5 space-y-4">
            <label className="block text-sm font-semibold text-slate-700">
              Job
              <select
                value={applicationId}
                onChange={(event) => {
                  setApplicationId(event.target.value);
                  setDraftId("");
                }}
                required
                disabled={saving || selectableApplications.length === 0}
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 font-normal"
              >
                <option value="">Choose a saved job</option>
                {selectableApplications.map((application) => (
                  <option key={application.id} value={application.id}>
                    {applicationLabel(application)}
                  </option>
                ))}
              </select>
            </label>

            {selectableApplications.length === 0 && (
              <p className="text-sm text-amber-700">
                You have no saved jobs yet.{" "}
                {onNavigate ? (
                  <button
                    type="button"
                    onClick={() => onNavigate("Find Jobs")}
                    className={linkBtn}
                  >
                    Find a job to save
                  </button>
                ) : (
                  "Save a job to your pipeline first."
                )}
              </p>
            )}

            {existingForApplication.length > 0 && (
              <p className="rounded-lg bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
                You already prepared this job (Execution #
                {existingForApplication[0].id},{" "}
                {getStage(existingForApplication[0]).label.toLowerCase()}).
                Preparing again creates a new snapshot.
              </p>
            )}

            <label className="block text-sm font-semibold text-slate-700">
              Resume
              <select
                value={resumeId}
                onChange={(event) => setResumeId(event.target.value)}
                required
                disabled={saving || resumes.length === 0}
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 font-normal"
              >
                <option value="">Choose a resume</option>
                {resumes.map((resume) => (
                  <option key={resume.id} value={resume.id}>
                    {resume.original_filename}
                  </option>
                ))}
              </select>
            </label>

            {resumes.length === 0 && (
              <p className="text-sm text-amber-700">
                You have no resumes yet.{" "}
                {onNavigate ? (
                  <button
                    type="button"
                    onClick={() => onNavigate("My Documents")}
                    className={linkBtn}
                  >
                    Upload one in My Documents
                  </button>
                ) : (
                  "Upload a resume in My Documents first."
                )}
              </p>
            )}

            <label className="block text-sm font-semibold text-slate-700">
              Cover letter (optional)
              <select
                value={draftId}
                onChange={(event) => setDraftId(event.target.value)}
                disabled={saving || !applicationId}
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 font-normal"
              >
                <option value="">No cover letter</option>
                {availableDrafts.map((draft) => (
                  <option key={draft.id} value={draft.id}>
                    Draft #{draft.id} · Updated{" "}
                    {new Date(draft.updated_at).toLocaleDateString()}
                  </option>
                ))}
              </select>
              {applicationId && availableDrafts.length === 0 && (
                <span className="mt-1 block text-xs font-normal text-slate-500">
                  No cover letter drafts exist for this job.{" "}
                  {onNavigate && (
                    <button
                      type="button"
                      onClick={() => onNavigate("Cover Letter Drafts")}
                      className={linkBtn}
                    >
                      Write one
                    </button>
                  )}
                </span>
              )}
            </label>

            <button
              type="submit"
              disabled={saving || !applicationId || !resumeId}
              className="rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Preparing..." : "Prepare application"}
            </button>
          </form>
        )}
      </section>

      {/* Steps 2-4: review, approve, submit */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              Your prepared applications
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Each card shows its progress and the next thing to do.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading || refreshing}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {!loading && executions.length > 0 && (
          <div
            role="group"
            aria-label="Filter prepared applications"
            className="mb-5 flex flex-wrap gap-2"
          >
            {filters.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                onClick={() => setFilter(key)}
                aria-pressed={filter === key}
                className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${
                  filter === key
                    ? "bg-violet-600 text-white"
                    : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                }`}
              >
                {label} ({counts[key]})
              </button>
            ))}
          </div>
        )}

        {loading ? (
          <p className="text-sm text-slate-500">Loading prepared applications...</p>
        ) : executions.length === 0 ? (
          <p className="rounded-xl bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
            Nothing prepared yet. Use “Prepare an application” above to start.
          </p>
        ) : visibleExecutions.length === 0 ? (
          <p className="rounded-xl bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
            No applications match this filter.
          </p>
        ) : (
          <div className="space-y-4">
            {visibleExecutions.map((execution) => (
              <ExecutionCard
                key={execution.id}
                execution={execution}
                expanded={expandedIds.has(execution.id)}
                busy={actionId === execution.id}
                confirmingApproval={confirmApprovalId === execution.id}
                handoff={handoff}
                handoffLoading={handoffLoadingId === execution.id}
                onToggleSnapshot={() => toggleSnapshot(execution.id)}
                onReview={() => void updateExecution(execution.id, "review")}
                onAskApproval={() => setConfirmApprovalId(execution.id)}
                onConfirmApproval={() =>
                  void updateExecution(execution.id, "approve")
                }
                onCancelApproval={() => setConfirmApprovalId(null)}
                onGenerateHandoff={() =>
                  void generateExtensionHandoff(execution.id)
                }
                onCopyToken={() => void copyToken()}
                onHideToken={() => setHandoff(null)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}