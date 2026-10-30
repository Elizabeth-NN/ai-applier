"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

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

type ApplicationExecution = {
  id: number;
  application_id: number;
  resume_id: number | null;
  cover_letter_draft_id: number | null;
  resume_filename_snapshot: string | null;
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

async function apiRequest<T>(
  path: string,
  token: string,
  options: RequestInit = {},
): Promise<T> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }

  const response = await fetch(
    `${apiUrl.replace(/\/$/, "")}${path}`,
    {
      ...options,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    },
  );

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

const statusStyles: Record<ExecutionStatus, string> = {
  prepared: "bg-slate-100 text-slate-700",
  approved: "bg-violet-100 text-violet-700",
  submitting: "bg-amber-100 text-amber-700",
  submitted: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
  needs_attention: "bg-orange-100 text-orange-700",
};

export default function ApplicationExecutions() {
  const { isLoaded, isSignedIn, getToken } = useAuth();

  const [applications, setApplications] = useState<Application[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [drafts, setDrafts] = useState<CoverLetterDraft[]>([]);
  const [executions, setExecutions] = useState<ApplicationExecution[]>([]);

  const [applicationId, setApplicationId] = useState("");
  const [resumeId, setResumeId] = useState("");
  const [draftId, setDraftId] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [actionId, setActionId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadData = useCallback(async () => {
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

    setApplications(loadedApplications);
    setResumes(loadedResumes);
    setDrafts(loadedDrafts);
    setExecutions(loadedExecutions);

    setApplicationId((current) =>
      current && loadedApplications.some((item) => String(item.id) === current)
        ? current
        : loadedApplications[0]
          ? String(loadedApplications[0].id)
          : "",
    );

    setResumeId((current) =>
      current && loadedResumes.some((item) => String(item.id) === current)
        ? current
        : loadedResumes[0]
          ? String(loadedResumes[0].id)
          : "",
    );
  }, [getToken]);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");

      try {
        await loadData();
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

  const availableDrafts = drafts.filter(
    (draft) => String(draft.application_id) === applicationId,
  );

  async function prepareExecution(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");

    if (!applicationId || !resumeId) {
      setError("Select an application and a resume first.");
      return;
    }

    setSaving(true);

    try {
      const token = await getToken();

      if (!token) throw new Error("Please sign in again.");

      const idempotencyKey = crypto.randomUUID();

      const created = await apiRequest<ApplicationExecution>(
        "/api/application-executions/prepare",
        token,
        {
          method: "POST",
          headers: {
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify({
            application_id: Number(applicationId),
            resume_id: Number(resumeId),
            cover_letter_draft_id: draftId ? Number(draftId) : null,
          }),
        },
      );

      setExecutions((current) => [
        created,
        ...current.filter((item) => item.id !== created.id),
      ]);

      setNotice(`Execution #${created.id} prepared successfully.`);
      setDraftId("");
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
    setError("");
    setNotice("");
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

      setNotice(
        action === "review"
          ? `Execution #${executionId} marked as reviewed.`
          : `Execution #${executionId} approved. No application was submitted.`,
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : `Could not ${action} this execution.`,
      );
    } finally {
      setActionId(null);
    }
  }

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

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
        <div className="mb-5">
          <h2 className="text-lg font-bold text-slate-900">
            Prepare an application
          </h2>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            Create a saved application snapshot using your selected resume and
            optional cover letter. Nothing is submitted to an employer.
          </p>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Loading your documents...</p>
        ) : (
          <form onSubmit={prepareExecution} className="space-y-4">
            <label className="block text-sm font-semibold text-slate-700">
              Saved application
              <select
                value={applicationId}
                onChange={(event) => {
                  setApplicationId(event.target.value);
                  setDraftId("");
                }}
                required
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 font-normal"
              >
                <option value="">Select an application</option>
                {applications.map((application) => (
                  <option key={application.id} value={application.id}>
                    Application #{application.id} · Job #{application.job_id} ·{" "}
                    {application.status}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm font-semibold text-slate-700">
              Resume
              <select
                value={resumeId}
                onChange={(event) => setResumeId(event.target.value)}
                required
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 font-normal"
              >
                <option value="">Select a resume</option>
                {resumes.map((resume) => (
                  <option key={resume.id} value={resume.id}>
                    {resume.original_filename}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm font-semibold text-slate-700">
              Cover-letter draft (optional)
              <select
                value={draftId}
                onChange={(event) => setDraftId(event.target.value)}
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
                <span className="mt-1 block text-xs font-normal text-slate-400">
                  No cover-letter drafts are linked to this application.
                </span>
              )}
            </label>

            {applications.length === 0 && (
              <p className="text-sm text-amber-700">
                Save a job to your application pipeline before preparing an
                execution.
              </p>
            )}

            {resumes.length === 0 && (
              <p className="text-sm text-amber-700">
                Upload a resume in My Documents before preparing an execution.
              </p>
            )}

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

      {error && (
        <p
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </p>
      )}

      {notice && (
        <p
          role="status"
          className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700"
        >
          {notice}
        </p>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-7">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              Prepared applications
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Review each snapshot before explicitly approving it.
            </p>
          </div>

          <button
            type="button"
            onClick={() => {
              setLoading(true);
              void loadData()
                .catch((err) =>
                  setError(
                    err instanceof Error ? err.message : "Refresh failed.",
                  ),
                )
                .finally(() => setLoading(false));
            }}
            disabled={loading}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            Refresh
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">Loading executions...</p>
        ) : executions.length === 0 ? (
          <p className="rounded-xl bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
            No application executions yet. Prepare one above to get started.
          </p>
        ) : (
          <div className="space-y-4">
            {executions.map((execution) => {
              const canReview = execution.status === "prepared";
              const canApprove =
                execution.status === "prepared" && execution.reviewed_at;

              return (
                <article
                  key={execution.id}
                  className="rounded-xl border border-slate-200 p-4 sm:p-5"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h3 className="font-bold text-slate-900">
                      Execution #{execution.id}
                    </h3>
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[execution.status]}`}
                    >
                      {execution.status.replace("_", " ")}
                    </span>
                  </div>

                  <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-slate-400">Application</dt>
                      <dd className="font-medium text-slate-700">
                        #{execution.application_id}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">Resume snapshot</dt>
                      <dd className="font-medium text-slate-700">
                        {execution.resume_filename_snapshot || "Not available"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">ATS platform</dt>
                      <dd className="font-medium text-slate-700">
                        {execution.ats_platform}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-slate-400">Created</dt>
                      <dd className="font-medium text-slate-700">
                        {new Date(execution.created_at).toLocaleString()}
                      </dd>
                    </div>
                  </dl>

                  <div className="mt-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Target application URL
                    </p>
                    <a
                      href={execution.target_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 block break-all text-sm font-medium text-violet-700 hover:underline"
                    >
                      {execution.target_url}
                    </a>
                  </div>

                  {execution.failure_reason && (
                    <p className="mt-3 text-sm text-red-600">
                      {execution.failure_reason}
                    </p>
                  )}

                  <div className="mt-5 flex flex-wrap gap-2">
                    {canReview && (
                      <button
                        type="button"
                        onClick={() =>
                          void updateExecution(execution.id, "review")
                        }
                        disabled={actionId === execution.id}
                        className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                      >
                        {actionId === execution.id
                          ? "Please wait..."
                          : "Mark as reviewed"}
                      </button>
                    )}

                    {canApprove && (
                      <button
                        type="button"
                        onClick={() =>
                          void updateExecution(execution.id, "approve")
                        }
                        disabled={actionId === execution.id}
                        className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700 disabled:opacity-50"
                      >
                        {actionId === execution.id
                          ? "Please wait..."
                          : "Approve snapshot"}
                      </button>
                    )}
                  </div>

                  {execution.reviewed_at && (
                    <p className="mt-3 text-xs text-emerald-700">
                      Reviewed{" "}
                      {new Date(execution.reviewed_at).toLocaleString()}
                    </p>
                  )}

                  {execution.approved_at && (
                    <p className="mt-1 text-xs text-violet-700">
                      Approved{" "}
                      {new Date(execution.approved_at).toLocaleString()}. This
                      does not mean the application was submitted.
                    </p>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
