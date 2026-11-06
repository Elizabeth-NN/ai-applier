"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";

type ApiJob = {
  id: number;
  title: string;
  company: string;
  location: string | null;
  application_url: string | null;
  remote_type: string | null;
  eligible_countries: string[] | null;
  eligibility_status: string;
  eligibility_evidence_url: string | null;
  listing_status: string;
  created_at: string;
};

type ApiApplication = {
  id: number;
  job_id: number;
  status: string;
};

type Resume = {
  id: number;
  original_filename: string;
};

type CoverLetterDraft = {
  id: number;
  application_id: number;
  title: string;
  content: string;
  updated_at: string;
};

type CandidateAnswer = {
  id: number;
  question_key: string;
  question_label: string;
  answer: string;
  is_user_authored: boolean;
  is_approved: boolean;
};

type Campaign = {
  id: number;
  name: string;
  status: "draft" | "active" | "paused" | "completed" | "archived";
  target_applications: number;
  starts_on: string;
  deadline_on: string;
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
  campaign_id: number | null;
  batch_item_id: number | null;
  status: ExecutionStatus;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
  failure_reason: string | null;
};

type BatchItem = {
  id: number;
  job_id: number;
  selected: boolean;
  approved_at: string | null;
  created_at: string;
  job: ApiJob;
};

type ApplicationBatch = {
  id: number;
  name: string;
  campaign_id: number | null;
  status: "draft" | "approved" | "archived";
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  items: BatchItem[];
};

type BatchPreparationItemResult = {
  batch_item_id: number;
  job_id: number;
  status: "prepared" | "already_prepared" | "failed";
  execution_id: number | null;
  execution_status: string | null;
  reason: string | null;
};

type BatchPreparationResult = {
  batch_id: number;
  prepared_count: number;
  already_prepared_count: number;
  failed_count: number;
  items: BatchPreparationItemResult[];
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
    throw new Error(
      data && typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status}).`,
    );
  }

  return data as T;
}

const executionLabels: Record<ExecutionStatus, string> = {
  prepared: "Prepared — awaiting review",
  approved: "Approved — awaiting handoff",
  submitting: "Submission in progress",
  submitted: "Submitted",
  failed: "Failed",
  needs_attention: "Needs attention",
};

const executionStyles: Record<ExecutionStatus, string> = {
  prepared: "bg-blue-100 text-blue-700",
  approved: "bg-violet-100 text-violet-700",
  submitting: "bg-amber-100 text-amber-700",
  submitted: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
  needs_attention: "bg-orange-100 text-orange-700",
};

function eligibilityLabel(job: ApiJob): string {
  if (job.eligibility_status === "eligible") return "Kenya eligibility verified";
  if (job.eligibility_status === "ineligible") return "Kenya eligibility: ineligible";
  return "Kenya eligibility: unverified";
}

function eligibilityStyle(job: ApiJob): string {
  if (job.eligibility_status === "eligible") {
    return "bg-emerald-50 text-emerald-700";
  }
  if (job.eligibility_status === "ineligible") {
    return "bg-red-50 text-red-700";
  }
  return "bg-amber-50 text-amber-800";
}

function listingLabel(status: string): string {
  if (status === "active") return "Listing active";
  if (status === "closed") return "Listing closed";
  return "Listing status unknown";
}

function latestExecutions(
  executions: ApplicationExecution[],
): Map<number, ApplicationExecution> {
  const latest = new Map<number, ApplicationExecution>();

  for (const execution of executions) {
    if (execution.batch_item_id === null) continue;

    const current = latest.get(execution.batch_item_id);

    if (
      !current ||
      new Date(execution.created_at).getTime() >
        new Date(current.created_at).getTime()
    ) {
      latest.set(execution.batch_item_id, execution);
    }
  }

  return latest;
}

type Props = {
  onOpenExecutions?: () => void;
};

export default function ApplicationBatches({ onOpenExecutions }: Props) {
  const { isLoaded, isSignedIn, getToken } = useAuth();

  const [applications, setApplications] = useState<ApiApplication[]>([]);
  const [jobs, setJobs] = useState<ApiJob[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [drafts, setDrafts] = useState<CoverLetterDraft[]>([]);
  const [candidateAnswers, setCandidateAnswers] = useState<CandidateAnswer[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [executions, setExecutions] = useState<ApplicationExecution[]>([]);
  const [batches, setBatches] = useState<ApplicationBatch[]>([]);

  const [activeBatchId, setActiveBatchId] = useState<number | null>(null);
  const [batchName, setBatchName] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const [createJobIds, setCreateJobIds] = useState<number[]>([]);
  const [addJobIds, setAddJobIds] = useState<number[]>([]);
  const [renameValue, setRenameValue] = useState("");

  const [expandedPreparationItemId, setExpandedPreparationItemId] =
    useState<number | null>(null);
  const [preparationResumeId, setPreparationResumeId] = useState("");
  const [preparationDraftId, setPreparationDraftId] = useState("");
  const [preparationAnswerIds, setPreparationAnswerIds] = useState<number[]>([]);
  const [preparingItemId, setPreparingItemId] = useState<number | null>(null);
  const [preparingBatch, setPreparingBatch] = useState(false);
  const [batchPreparationResult, setBatchPreparationResult] =
    useState<BatchPreparationResult | null>(null);
  const preparationIdempotency = useRef<{
    signature: string;
    key: string;
  } | null>(null);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const activeBatch =
    batches.find((batch) => batch.id === activeBatchId) ?? null;

  const savedJobs = useMemo(() => {
    const savedIds = new Set(
      applications
        .filter((application) => application.status === "saved")
        .map((application) => application.job_id),
    );

    return jobs.filter((job) => savedIds.has(job.id));
  }, [applications, jobs]);

  const executionsByItem = useMemo(
    () => latestExecutions(executions),
    [executions],
  );

  const availableToAdd = useMemo(() => {
    if (!activeBatch) return [];
    const existingIds = new Set(activeBatch.items.map((item) => item.job_id));
    return savedJobs.filter((job) => !existingIds.has(job.id));
  }, [activeBatch, savedJobs]);

  const sessionProgress = useMemo(() => {
    if (!activeBatch) return null;

    const selectedItems = activeBatch.items.filter((item) => item.selected);
    const counts = {
      submitted: 0,
      prepared: 0,
      approved: 0,
      submitting: 0,
      failed: 0,
      needs_attention: 0,
      notPrepared: 0,
    };

    for (const item of selectedItems) {
      const execution = executionsByItem.get(item.id);

      if (!execution) {
        counts.notPrepared += 1;
      } else {
        counts[execution.status] += 1;
      }
    }

    return { selected: selectedItems.length, ...counts };
  }, [activeBatch, executionsByItem]);

  const loadData = useCallback(async () => {
    const token = await getToken();

    if (!token) {
      throw new Error("Your session has expired. Please sign in again.");
    }

    const [
      loadedApplications,
      loadedBatches,
      loadedCampaigns,
      loadedExecutions,
      loadedResumes,
      loadedDrafts,
      loadedCandidateAnswers,
    ] = await Promise.all([
      apiRequest<ApiApplication[]>("/api/applications?limit=100", token),
      apiRequest<ApplicationBatch[]>("/api/application-batches?limit=100", token),
      apiRequest<Campaign[]>("/api/application-campaigns?limit=100", token),
      apiRequest<ApplicationExecution[]>(
        "/api/application-executions?limit=100",
        token,
      ),
      apiRequest<Resume[]>("/api/resumes", token),
      apiRequest<CoverLetterDraft[]>("/api/cover-letter-drafts?limit=100", token),
      apiRequest<CandidateAnswer[]>("/api/candidate-answers?limit=100", token),
    ]);

    const jobIds = [
      ...new Set(loadedApplications.map((application) => application.job_id)),
    ];

    const loadedJobs = await Promise.all(
      jobIds.map((jobId) =>
        apiRequest<ApiJob>(`/api/jobs/${jobId}`, token),
      ),
    );

    setApplications(loadedApplications);
    setJobs(loadedJobs);
    setResumes(loadedResumes);
    setDrafts(loadedDrafts);
    setCandidateAnswers(loadedCandidateAnswers);
    setPreparationResumeId((current) =>
      current && loadedResumes.some((resume) => String(resume.id) === current)
        ? current
        : loadedResumes[0]
          ? String(loadedResumes[0].id)
          : "",
    );
    setExecutions(loadedExecutions);
    setBatches(loadedBatches);

    const initialBatch = loadedBatches[0] ?? null;
    setActiveBatchId(initialBatch?.id ?? null);
    setRenameValue(initialBatch?.name ?? "");
    setAddJobIds([]);

    setCampaignId((current) => {
      if (current && loadedCampaigns.some((item) => item.id === Number(current))) {
        return current;
      }

      const active = loadedCampaigns.find((item) => item.status === "active");
      return active ? String(active.id) : "";
    });
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
            err instanceof Error ? err.message : "Could not load application sessions.",
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

  function updateBatch(updated: ApplicationBatch) {
    setBatches((current) =>
      current.map((batch) => batch.id === updated.id ? updated : batch),
    );
  }

  async function prepareApprovedBatch() {
    if (
      !activeBatch ||
      activeBatch.status !== "approved" ||
      preparingBatch ||
      preparingItemId !== null
    ) {
      return;
    }

    const selectedCount = activeBatch.items.filter(
      (item) => item.selected && item.approved_at !== null,
    ).length;

    if (selectedCount === 0) {
      setError("This session has no selected, approved jobs to prepare.");
      return;
    }

    if (!preparationResumeId) {
      setError("Upload or select a resume before preparing this session.");
      return;
    }

    setError("");
    setNotice("");
    setPreparingBatch(true);
    setBatchPreparationResult(null);

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const result = await apiRequest<BatchPreparationResult>(
        `/api/application-batches/${activeBatch.id}/prepare`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            resume_id: Number(preparationResumeId),
            candidate_answer_ids: [...preparationAnswerIds].sort(
              (a, b) => a - b,
            ),
          }),
        },
      );

      setBatchPreparationResult(result);

      const refreshedExecutions = await apiRequest<ApplicationExecution[]>(
        "/api/application-executions?limit=100",
        token,
      );
      setExecutions(refreshedExecutions);

      setNotice(
        `Batch preparation finished: ${result.prepared_count} prepared, ` +
        `${result.already_prepared_count} already prepared, ` +
        `${result.failed_count} failed. ` +
        "Review prepared snapshots in Application Executions.",
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not prepare this application session.",
      );
    } finally {
      setPreparingBatch(false);
    }
  }

  async function prepareSessionItem(item: BatchItem) {
    if (
      !activeBatch ||
      activeBatch.status !== "approved" ||
      !item.selected ||
      preparingItemId !== null
    ) {
      return;
    }

    const application = applications.find(
      (candidate) => candidate.job_id === item.job_id,
    );

    if (!application) {
      setError("This job has no saved application record. Refresh the session and try again.");
      return;
    }

    if (!preparationResumeId) {
      setError("Upload or select a resume before preparing this application.");
      return;
    }

    setError("");
    setNotice("");
    setPreparingItemId(item.id);

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const selectedAnswerIds = [...preparationAnswerIds].sort((a, b) => a - b);
      const signature = [
        activeBatch.id,
        item.id,
        application.id,
        preparationResumeId,
        preparationDraftId,
        selectedAnswerIds.join(","),
      ].join(":");

      if (preparationIdempotency.current?.signature !== signature) {
        preparationIdempotency.current = {
          signature,
          key: crypto.randomUUID(),
        };
      }

      const created = await apiRequest<ApplicationExecution>(
        "/api/application-executions/prepare",
        token,
        {
          method: "POST",
          headers: {
            "Idempotency-Key": preparationIdempotency.current.key,
          },
          body: JSON.stringify({
            application_id: application.id,
            resume_id: Number(preparationResumeId),
            cover_letter_draft_id: preparationDraftId
              ? Number(preparationDraftId)
              : null,
            batch_item_id: item.id,
            campaign_id: activeBatch.campaign_id,
            candidate_answer_ids: selectedAnswerIds,
          }),
        },
      );

      preparationIdempotency.current = null;
      setExecutions((current) => [
        created,
        ...current.filter((execution) => execution.id !== created.id),
      ]);
      setExpandedPreparationItemId(null);
      setPreparationDraftId("");
      setPreparationAnswerIds([]);
      setNotice(
        `Application prepared for ${item.job.title}. Review its snapshot in Application Executions before taking any further action.`,
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not prepare this application.",
      );
    } finally {
      setPreparingItemId(null);
    }
  }

  async function createSession(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (createJobIds.length === 0) {
      setError("Select at least one saved job to create a session.");
      return;
    }

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const created = await apiRequest<ApplicationBatch>(
        "/api/application-batches",
        token,
        {
          method: "POST",
          body: JSON.stringify({
            name: batchName.trim(),
            job_ids: createJobIds,
            campaign_id: campaignId ? Number(campaignId) : null,
          }),
        },
      );

      setBatches((current) => [created, ...current]);
      setActiveBatchId(created.id);
      setRenameValue(created.name);
      setAddJobIds([]);
      setBatchName("");
      setCreateJobIds([]);
      setNotice("Draft session created. Review the jobs before approving the selection.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the session.");
    } finally {
      setSaving(false);
    }
  }

  async function renameSession() {
    if (!activeBatch || activeBatch.status !== "draft") return;

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApplicationBatch>(
        `/api/application-batches/${activeBatch.id}`,
        token,
        {
          method: "PATCH",
          body: JSON.stringify({ name: renameValue.trim() }),
        },
      );

      updateBatch(updated);
      setRenameValue(updated.name);
      setNotice("Session name updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rename the session.");
    } finally {
      setSaving(false);
    }
  }

  async function addJobs() {
    if (!activeBatch || activeBatch.status !== "draft" || addJobIds.length === 0) {
      return;
    }

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApplicationBatch>(
        `/api/application-batches/${activeBatch.id}/items`,
        token,
        {
          method: "POST",
          body: JSON.stringify({ job_ids: addJobIds }),
        },
      );

      updateBatch(updated);
      setAddJobIds([]);
      setNotice("Jobs added to the draft session.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add jobs.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleItem(item: BatchItem, selected: boolean) {
    if (!activeBatch || activeBatch.status !== "draft") return;

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApplicationBatch>(
        `/api/application-batches/${activeBatch.id}/items/${item.id}`,
        token,
        {
          method: "PATCH",
          body: JSON.stringify({ selected }),
        },
      );

      updateBatch(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the selection.");
    } finally {
      setSaving(false);
    }
  }

  async function removeItem(item: BatchItem) {
    if (!activeBatch || activeBatch.status !== "draft") return;

    const confirmed = window.confirm(
      `Remove "${item.job.title}" from this draft session?`,
    );
    if (!confirmed) return;

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApplicationBatch>(
        `/api/application-batches/${activeBatch.id}/items/${item.id}`,
        token,
        { method: "DELETE" },
      );

      updateBatch(updated);
      setNotice("Job removed from the session.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the job.");
    } finally {
      setSaving(false);
    }
  }

  async function approveSession() {
    if (!activeBatch || activeBatch.status !== "draft") return;

    const selectedCount = activeBatch.items.filter((item) => item.selected).length;

    if (selectedCount === 0) {
      setError("Select at least one job before approving this session.");
      return;
    }

    const confirmed = window.confirm(
      `Approve ${selectedCount} selected job(s) in "${activeBatch.name}"? This records approval only. It will not submit applications.`,
    );

    if (!confirmed) return;

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApplicationBatch>(
        `/api/application-batches/${activeBatch.id}/approve`,
        token,
        { method: "POST" },
      );

      updateBatch(updated);
      setNotice("Session approved. No applications have been submitted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not approve the session.");
    } finally {
      setSaving(false);
    }
  }

  async function archiveSession() {
    if (!activeBatch || activeBatch.status !== "approved") return;

    const confirmed = window.confirm(
      `Archive "${activeBatch.name}"? Its jobs and execution history will be preserved.`,
    );
    if (!confirmed) return;

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();
      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApplicationBatch>(
        `/api/application-batches/${activeBatch.id}/archive`,
        token,
        { method: "POST" },
      );

      updateBatch(updated);
      setNotice("Session archived. Its history has been preserved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not archive the session.");
    } finally {
      setSaving(false);
    }
  }

  if (!isLoaded || (isSignedIn && loading)) {
    return <p className="text-sm text-slate-500">Loading application sessions...</p>;
  }

  if (!isSignedIn) {
    return <p className="text-sm text-slate-500">Sign in to manage application sessions.</p>;
  }

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Application Sessions</h2>
        <p className="mt-1 text-sm text-slate-500">
          Organise a focused application session, screen saved jobs, approve your
          selection, and track execution progress. Approval never submits applications.
        </p>
      </div>

      {error && (
        <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {notice && (
        <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {notice}
        </p>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        <h3 className="font-bold text-slate-900">Start an application session</h3>
        <p className="mt-1 text-sm text-slate-500">
          Sessions contain jobs already saved in your application pipeline.
          Jobs that have moved beyond the saved status are excluded.
        </p>

        <form onSubmit={createSession} className="mt-4 space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block text-sm font-medium text-slate-700">
              Session name
              <input
                required
                minLength={1}
                maxLength={150}
                value={batchName}
                onChange={(event) => setBatchName(event.target.value)}
                placeholder="e.g. Backend applications — November"
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-violet-400"
              />
            </label>

            <label className="block text-sm font-medium text-slate-700">
              Campaign
              <select
                value={campaignId}
                onChange={(event) => setCampaignId(event.target.value)}
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 outline-none focus:border-violet-400"
              >
                <option value="">No campaign linked</option>
                {campaigns.map((campaign) => (
                  <option key={campaign.id} value={campaign.id}>
                    {campaign.name} ({campaign.status})
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-semibold text-slate-700">
                Saved jobs ({savedJobs.length} available)
              </span>
              <span className="text-xs text-slate-500">
                {createJobIds.length} selected
              </span>
            </div>

            <div className="max-h-80 space-y-2 overflow-y-auto">
              {savedJobs.length === 0 && (
                <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">
                  No saved jobs available. Save jobs to your application pipeline first.
                </p>
              )}

              {savedJobs.map((job) => (
                <label
                  key={job.id}
                  className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-100 p-3 hover:bg-slate-50"
                >
                  <input
                    type="checkbox"
                    checked={createJobIds.includes(job.id)}
                    onChange={(event) => {
                      setCreateJobIds((current) =>
                        event.target.checked
                          ? [...current, job.id]
                          : current.filter((id) => id !== job.id),
                      );
                    }}
                    className="mt-1 accent-violet-600"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold text-slate-800">
                      {job.title}
                    </span>
                    <span className="block text-xs text-slate-500">
                      {job.company} · {job.location || "Location not specified"}
                    </span>
                    <span className="mt-1 flex flex-wrap gap-1.5">
                      <span className={`rounded-full px-2 py-0.5 text-xs ${eligibilityStyle(job)}`}>
                        {eligibilityLabel(job)}
                      </span>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                        {listingLabel(job.listing_status)}
                      </span>
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          <button
            type="submit"
            disabled={saving || createJobIds.length === 0 || !batchName.trim()}
            className="w-full rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving..." : `Create session (${createJobIds.length} selected)`}
          </button>
        </form>
      </section>

      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.5fr]">
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="font-bold text-slate-900">Your sessions</h3>

          {batches.length === 0 ? (
            <p className="mt-3 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
              No sessions yet. Create one to start organising your applications.
            </p>
          ) : (
            <div className="mt-3 space-y-2">
              {batches.map((batch) => {
                const selectedCount = batch.items.filter((item) => item.selected).length;
                const campaign = campaigns.find((item) => item.id === batch.campaign_id);

                return (
                  <button
                    key={batch.id}
                    type="button"
                    onClick={() => {
                      setActiveBatchId(batch.id);
                      setRenameValue(batch.name);
                      setAddJobIds([]);
                    }}
                    className={`w-full rounded-xl border p-3 text-left ${
                      activeBatchId === batch.id
                        ? "border-violet-300 bg-violet-50"
                        : "border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-3">
                      <span className="font-semibold text-slate-800">{batch.name}</span>
                      <span className={`rounded-full px-2 py-1 text-xs font-semibold ${
                        batch.status === "approved"
                          ? "bg-emerald-100 text-emerald-700"
                          : batch.status === "archived"
                            ? "bg-slate-200 text-slate-600"
                            : "bg-amber-100 text-amber-700"
                      }`}>
                        {batch.status}
                      </span>
                    </span>
                    <span className="mt-1 block text-xs text-slate-500">
                      {selectedCount} selected · {batch.items.length} total jobs
                    </span>
                    {campaign && (
                      <span className="mt-1 block text-xs text-violet-700">
                        Campaign: {campaign.name}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </section>

        {activeBatch ? (
          <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                {activeBatch.status === "draft" ? (
                  <div className="flex flex-wrap gap-2">
                    <input
                      value={renameValue}
                      onChange={(event) => setRenameValue(event.target.value)}
                      maxLength={150}
                      aria-label="Session name"
                      className="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2 text-lg font-bold text-slate-900 outline-none focus:border-violet-400"
                    />
                    <button
                      type="button"
                      onClick={() => void renameSession()}
                      disabled={saving || !renameValue.trim() || renameValue.trim() === activeBatch.name}
                      className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                    >
                      Rename
                    </button>
                  </div>
                ) : (
                  <h3 className="text-lg font-bold text-slate-900">{activeBatch.name}</h3>
                )}

                <p className="mt-1 text-sm text-slate-500">
                  {activeBatch.items.filter((item) => item.selected).length} selected
                  of {activeBatch.items.length} jobs · {activeBatch.status}
                </p>
              </div>

              {activeBatch.status === "draft" ? (
                <button
                  type="button"
                  onClick={() => void approveSession()}
                  disabled={saving || !activeBatch.items.some((item) => item.selected)}
                  className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Approve selected jobs
                </button>
              ) : activeBatch.status === "approved" ? (
                <button
                  type="button"
                  onClick={() => void archiveSession()}
                  disabled={saving}
                  className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  Archive session
                </button>
              ) : (
                <span className="text-sm font-semibold text-slate-500">
                  Archived
                </span>
              )}
            </div>

            {activeBatch.campaign_id && (
              <p className="mt-3 rounded-xl bg-violet-50 p-3 text-sm text-violet-800">
                Linked campaign:{" "}
                {campaigns.find((item) => item.id === activeBatch.campaign_id)?.name
                  ?? `Campaign #${activeBatch.campaign_id}`}
              </p>
            )}

            {activeBatch.status !== "draft" && activeBatch.approved_at && (
              <p className="mt-2 text-xs text-slate-500">
                Approved {new Date(activeBatch.approved_at).toLocaleString()}
              </p>
            )}

            {activeBatch.status === "approved" && (
              <div className="mt-5 rounded-xl border border-violet-200 bg-violet-50/50 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h4 className="text-sm font-bold text-slate-800">
                      Prepare selected jobs
                    </h4>
                    <p className="mt-1 text-xs text-slate-600">
                      Only selected, approved jobs are included. Existing
                      executions are recognised rather than duplicated.
                      New snapshots still require your review and approval.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void prepareApprovedBatch()}
                    disabled={
                      preparingBatch ||
                      preparingItemId !== null ||
                      !preparationResumeId ||
                      !activeBatch.items.some(
                        (item) => item.selected && item.approved_at !== null,
                      )
                    }
                    className="shrink-0 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {preparingBatch ? "Preparing jobs..." : "Prepare selected jobs"}
                  </button>
                </div>

                {!preparationResumeId && (
                  <p className="mt-2 text-xs text-amber-800">
                    Upload a resume before preparing this session.
                  </p>
                )}

                {batchPreparationResult?.batch_id === activeBatch.id && (
                  <div className="mt-4 border-t border-violet-200 pt-3">
                    <div className="grid grid-cols-3 gap-2">
                      <ProgressCount
                        label="Prepared"
                        value={batchPreparationResult.prepared_count}
                      />
                      <ProgressCount
                        label="Already prepared"
                        value={batchPreparationResult.already_prepared_count}
                      />
                      <ProgressCount
                        label="Failed"
                        value={batchPreparationResult.failed_count}
                      />
                    </div>

                    <div className="mt-3 space-y-2">
                      {batchPreparationResult.items.map((itemResult) => {
                        const batchItem = activeBatch.items.find(
                          (item) => item.id === itemResult.batch_item_id,
                        );

                        return (
                          <div
                            key={itemResult.batch_item_id}
                            className="rounded-lg border border-slate-200 bg-white p-3 text-xs"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="font-semibold text-slate-800">
                                {batchItem?.job.title ?? `Job #${itemResult.job_id}`}
                              </span>
                              <span className={`rounded-full px-2 py-1 font-semibold ${
                                itemResult.status === "prepared"
                                  ? "bg-blue-100 text-blue-700"
                                  : itemResult.status === "already_prepared"
                                    ? "bg-slate-100 text-slate-700"
                                    : "bg-red-100 text-red-700"
                              }`}>
                                {itemResult.status === "already_prepared"
                                  ? "Already prepared"
                                  : itemResult.status === "prepared"
                                    ? "Newly prepared"
                                    : "Failed"}
                              </span>
                            </div>
                            {itemResult.execution_id !== null && (
                              <button
                                type="button"
                                onClick={onOpenExecutions}
                                disabled={!onOpenExecutions}
                                className="mt-1 text-left font-medium text-violet-700 underline decoration-violet-300 underline-offset-2 hover:text-violet-900 disabled:cursor-default disabled:no-underline disabled:opacity-70"
                              >
                                View execution #{itemResult.execution_id}
                                {itemResult.execution_status
                                  ? ` · ${itemResult.execution_status}`
                                  : ""}
                              </button>
                            )}
                            {itemResult.reason && (
                              <p className="mt-1 text-slate-600">
                                {itemResult.reason}
                              </p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {sessionProgress && activeBatch.status !== "draft" && (
              <div className="mt-5 rounded-xl bg-slate-50 p-4">
                <h4 className="text-sm font-bold text-slate-800">Session execution status</h4>
                <p className="mt-1 text-xs text-slate-500">
                  Counts reflect the latest execution associated with each selected job.
                </p>
                <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <ProgressCount label="Submitted" value={sessionProgress.submitted} />
                  <ProgressCount label="Prepared" value={sessionProgress.prepared} />
                  <ProgressCount label="Approved" value={sessionProgress.approved} />
                  <ProgressCount label="Submitting" value={sessionProgress.submitting} />
                  <ProgressCount label="Failed" value={sessionProgress.failed} />
                  <ProgressCount label="Needs attention" value={sessionProgress.needs_attention} />
                  <ProgressCount label="Not prepared" value={sessionProgress.notPrepared} />
                </div>
              </div>
            )}

            {activeBatch.status === "draft" && (
              <div className="mt-5 rounded-xl border border-slate-200 p-4">
                <h4 className="text-sm font-bold text-slate-800">Add saved jobs</h4>
                <p className="mt-1 text-xs text-slate-500">
                  Only saved jobs not already in this session are available.
                </p>

                {availableToAdd.length === 0 ? (
                  <p className="mt-3 text-sm text-slate-500">
                    No additional saved jobs available.
                  </p>
                ) : (
                  <>
                    <div className="mt-3 max-h-48 space-y-2 overflow-y-auto">
                      {availableToAdd.map((job) => (
                        <label key={job.id} className="flex items-center gap-2 text-sm text-slate-700">
                          <input
                            type="checkbox"
                            checked={addJobIds.includes(job.id)}
                            onChange={(event) => {
                              setAddJobIds((current) =>
                                event.target.checked
                                  ? [...current, job.id]
                                  : current.filter((id) => id !== job.id),
                              );
                            }}
                            className="accent-violet-600"
                          />
                          <span>{job.title} — {job.company}</span>
                        </label>
                      ))}
                    </div>
                    <button
                      type="button"
                      onClick={() => void addJobs()}
                      disabled={saving || addJobIds.length === 0}
                      className="mt-3 rounded-xl border border-violet-200 px-4 py-2 text-sm font-semibold text-violet-700 hover:bg-violet-50 disabled:opacity-50"
                    >
                      Add {addJobIds.length || ""} selected jobs
                    </button>
                  </>
                )}
              </div>
            )}

            <div className="mt-5 space-y-3">
              <h4 className="text-sm font-bold text-slate-800">Session jobs</h4>

              {activeBatch.items.length === 0 && (
                <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
                  This session has no jobs yet.
                </p>
              )}

              {activeBatch.items.map((item) => {
                const execution = executionsByItem.get(item.id);
                const application = applications.find(
                  (candidate) => candidate.job_id === item.job_id,
                );
                const availableDrafts = drafts.filter(
                  (draft) => draft.application_id === application?.id,
                );
                const approvedAnswers = candidateAnswers.filter(
                  (answer) => answer.is_user_authored && answer.is_approved,
                );
                const canPrepare =
                  activeBatch.status === "approved" &&
                  item.selected &&
                  (!execution ||
                    execution.status === "failed" ||
                    execution.status === "needs_attention");

                return (
                  <div key={item.id} className="rounded-xl border border-slate-200 p-3">
                    <div className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={item.selected}
                        disabled={saving || activeBatch.status !== "draft"}
                        onChange={(event) => void toggleItem(item, event.target.checked)}
                        aria-label={`Select ${item.job.title}`}
                        className="mt-1 accent-violet-600"
                      />

                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-slate-800">{item.job.title}</p>
                        <p className="text-sm text-slate-500">
                          {item.job.company} · {item.job.location || "Location not specified"}
                        </p>

                        <div className="mt-2 flex flex-wrap gap-1.5">
                          <span className={`rounded-full px-2 py-1 text-xs ${eligibilityStyle(item.job)}`}>
                            {eligibilityLabel(item.job)}
                          </span>
                          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">
                            {listingLabel(item.job.listing_status)}
                          </span>
                          {item.job.remote_type && (
                            <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">
                              {item.job.remote_type}
                            </span>
                          )}
                        </div>

                        {item.job.eligible_countries?.length ? (
                          <p className="mt-2 text-xs text-slate-500">
                            Eligible countries listed: {item.job.eligible_countries.join(", ")}
                          </p>
                        ) : (
                          <p className="mt-2 text-xs text-slate-500">
                            No eligible-country list provided by the source.
                          </p>
                        )}

                        {item.job.eligibility_evidence_url && (
                          <a
                            href={item.job.eligibility_evidence_url}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-1 inline-block text-xs font-medium text-violet-700 hover:underline"
                          >
                            View eligibility evidence
                          </a>
                        )}

                        <div className="mt-2">
                          {execution ? (
                            <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${executionStyles[execution.status]}`}>
                              {executionLabels[execution.status]}
                            </span>
                          ) : (
                            <span className="text-xs text-slate-500">
                              No execution prepared
                            </span>
                          )}
                        </div>

                        {execution?.failure_reason && (
                          <p className="mt-2 text-xs text-red-700">
                            {execution.failure_reason}
                          </p>
                        )}

                        {item.job.application_url ? (
                          <a
                            href={item.job.application_url}
                            target="_blank"
                            rel="noreferrer"
                            className="mt-2 inline-block text-xs font-semibold text-violet-700 hover:underline"
                          >
                            Open employer application page
                          </a>
                        ) : (
                          <p className="mt-2 text-xs text-amber-700">
                            No verified application URL is recorded.
                          </p>
                        )}

                        {canPrepare && (
                          <div className="mt-3">
                            <button
                              type="button"
                              onClick={() => {
                                setError("");
                                setNotice("");
                                setExpandedPreparationItemId((current) =>
                                  current === item.id ? null : item.id,
                                );
                                setPreparationDraftId("");
                                setPreparationAnswerIds([]);
                              }}
                              disabled={preparingItemId !== null}
                              className="rounded-lg bg-violet-600 px-3 py-2 text-xs font-semibold text-white hover:bg-violet-700 disabled:opacity-50"
                            >
                              {expandedPreparationItemId === item.id
                                ? "Close preparation"
                                : "Prepare application"}
                            </button>

                            {expandedPreparationItemId === item.id && (
                              <div className="mt-3 space-y-3 rounded-xl border border-violet-200 bg-violet-50/50 p-3">
                                <p className="text-xs leading-5 text-slate-600">
                                  This creates a reviewable snapshot linked to this session.
                                  It does not submit the application or contact the employer.
                                </p>

                                {!application ? (
                                  <p className="text-sm text-red-700">
                                    No application record was found for this job. Refresh the session before continuing.
                                  </p>
                                ) : resumes.length === 0 ? (
                                  <p className="text-sm text-amber-800">
                                    Upload a resume in My Documents before preparing this application.
                                  </p>
                                ) : (
                                  <>
                                    <label className="block text-xs font-semibold text-slate-700">
                                      Resume
                                      <select
                                        value={preparationResumeId}
                                        onChange={(event) =>
                                          setPreparationResumeId(event.target.value)
                                        }
                                        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-normal"
                                      >
                                        {resumes.map((resume) => (
                                          <option key={resume.id} value={resume.id}>
                                            {resume.original_filename}
                                          </option>
                                        ))}
                                      </select>
                                    </label>

                                    <label className="block text-xs font-semibold text-slate-700">
                                      Cover letter draft (optional)
                                      <select
                                        value={preparationDraftId}
                                        onChange={(event) =>
                                          setPreparationDraftId(event.target.value)
                                        }
                                        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-normal"
                                      >
                                        <option value="">No cover letter draft</option>
                                        {availableDrafts.map((draft) => (
                                          <option key={draft.id} value={draft.id}>
                                            {draft.title} · Updated{" "}
                                            {new Date(draft.updated_at).toLocaleDateString()}
                                          </option>
                                        ))}
                                      </select>
                                    </label>

                                    <fieldset className="space-y-2">
                                      <legend className="text-xs font-semibold text-slate-700">
                                        Approved reusable answers (optional)
                                      </legend>
                                      {approvedAnswers.length === 0 ? (
                                        <p className="text-xs text-slate-500">
                                          No user-authored approved answers are available.
                                        </p>
                                      ) : (
                                        approvedAnswers.map((answer) => (
                                          <label
                                            key={answer.id}
                                            className="flex items-start gap-2 rounded-lg bg-white p-2 text-xs text-slate-700"
                                          >
                                            <input
                                              type="checkbox"
                                              checked={preparationAnswerIds.includes(answer.id)}
                                              onChange={(event) =>
                                                setPreparationAnswerIds((current) =>
                                                  event.target.checked
                                                    ? [...current, answer.id]
                                                    : current.filter((id) => id !== answer.id),
                                                )
                                              }
                                              className="mt-0.5 accent-violet-600"
                                            />
                                            <span className="min-w-0">
                                              <span className="block font-semibold">
                                                {answer.question_label}
                                              </span>
                                              <span className="mt-1 block whitespace-pre-wrap text-slate-500">
                                                {answer.answer}
                                              </span>
                                            </span>
                                          </label>
                                        ))
                                      )}
                                    </fieldset>

                                    <button
                                      type="button"
                                      onClick={() => void prepareSessionItem(item)}
                                      disabled={
                                        preparingItemId !== null ||
                                        !preparationResumeId ||
                                        resumes.length === 0
                                      }
                                      className="w-full rounded-lg bg-violet-600 px-3 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                                    >
                                      {preparingItemId === item.id
                                        ? "Preparing snapshot..."
                                        : "Create reviewable snapshot"}
                                    </button>
                                  </>
                                )}
                              </div>
                            )}
                          </div>
                        )}

                        {execution &&
                          ["prepared", "approved", "submitting", "submitted"].includes(
                            execution.status,
                          ) && (
                            <p className="mt-2 text-xs text-slate-500">
                              This execution already exists. Review it in Application Executions before preparing another snapshot.
                            </p>
                          )}
                      </div>

                      {activeBatch.status === "draft" && (
                        <button
                          type="button"
                          onClick={() => void removeItem(item)}
                          disabled={saving}
                          className="shrink-0 rounded-lg px-2 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            <p className="mt-5 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">
              Approval records your decision only. It does not send applications,
              contact employers, or mark jobs as applied. A submission is counted
              toward campaign progress only after its execution is confirmed as submitted.
              Unknown Kenya eligibility is not treated as verified.
            </p>
          </section>
        ) : (
          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <p className="text-sm text-slate-500">
              Select a session to review its jobs and execution progress.
            </p>
          </section>
        )}
      </div>
    </section>
  );
}

function ProgressCount({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-white p-3">
      <p className="text-xl font-bold tabular-nums text-slate-900">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{label}</p>
    </div>
  );
}
