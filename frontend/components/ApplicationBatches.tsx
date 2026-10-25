"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

type ApiJob = {
  id: number;
  title: string;
  company: string;
  location: string | null;
  created_at: string;
};

type ApiApplication = {
  id: number;
  job_id: number;
  status: string;
};

type BatchItem = {
  id: number;
  job_id: number;
  selected: boolean;
  approved_at: string | null;
  job: ApiJob;
};

type ApplicationBatch = {
  id: number;
  name: string;
  status: "draft" | "approved" | "archived";
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  items: BatchItem[];
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
    throw new Error(
      data && typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status}).`,
    );
  }

  return data as T;
}

export default function ApplicationBatches() {
  const { isLoaded, isSignedIn, getToken } = useAuth();

  const [applications, setApplications] = useState<ApiApplication[]>([]);
  const [jobs, setJobs] = useState<ApiJob[]>([]);
  const [batches, setBatches] = useState<ApplicationBatch[]>([]);
  const [activeBatchId, setActiveBatchId] = useState<number | null>(null);
  const [selectedJobIds, setSelectedJobIds] = useState<number[]>([]);
  const [batchName, setBatchName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const activeBatch =
    batches.find((batch) => batch.id === activeBatchId) ?? null;

  const loadData = useCallback(async () => {
    const token = await getToken();

    if (!token) {
      throw new Error("Your session has expired. Please sign in again.");
    }

    const [loadedApplications, loadedBatches] = await Promise.all([
      apiRequest<ApiApplication[]>("/api/applications?limit=100", token),
      apiRequest<ApplicationBatch[]>("/api/application-batches?limit=100", token),
    ]);

    const jobIds = [...new Set(loadedApplications.map((item) => item.job_id))];

    const loadedJobs = await Promise.all(
      jobIds.map((jobId) => apiRequest<ApiJob>(`/api/jobs/${jobId}`, token)),
    );

    setApplications(loadedApplications);
    setJobs(loadedJobs);
    setBatches(loadedBatches);

    setActiveBatchId((currentId) => {
      if (currentId !== null && loadedBatches.some((batch) => batch.id === currentId)) {
        return currentId;
      }

      return loadedBatches[0]?.id ?? null;
    });
  }, [getToken]);

  useEffect(() => {
    if (!isLoaded) return;

    if (!isSignedIn) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");

      try {
        await loadData();
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load batches.");
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

  async function createBatch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (selectedJobIds.length === 0) {
      setError("Select at least one tracked job to create a batch.");
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
            job_ids: selectedJobIds,
          }),
        },
      );

      setBatches((current) => [created, ...current]);
      setActiveBatchId(created.id);
      setBatchName("");
      setSelectedJobIds([]);
      setNotice("Draft batch created. Review its jobs and select the ones to approve.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the batch.");
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

      setBatches((current) =>
        current.map((batch) => batch.id === updated.id ? updated : batch),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the selection.");
    } finally {
      setSaving(false);
    }
  }

  async function approveBatch() {
    if (!activeBatch || activeBatch.status !== "draft") return;

    const selectedCount = activeBatch.items.filter((item) => item.selected).length;

    if (selectedCount === 0) {
      setError("Select at least one job before approving this batch.");
      return;
    }

    const confirmed = window.confirm(
      `Approve ${selectedCount} selected job(s) in "${activeBatch.name}"? This records approval only; it will not submit applications.`,
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

      setBatches((current) =>
        current.map((batch) => batch.id === updated.id ? updated : batch),
      );
      setNotice("Batch approved. No applications have been submitted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not approve the batch.");
    } finally {
      setSaving(false);
    }
  }

  if (!isLoaded || loading) {
    return <p className="text-sm text-slate-500">Loading application batches...</p>;
  }

  if (!isSignedIn) {
    return <p className="text-sm text-slate-500">Sign in to manage application batches.</p>;
  }

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Application Batches</h2>
        <p className="mt-1 text-sm text-slate-500">
          Group tracked jobs, review your choices, and explicitly approve a batch.
          Approval does not submit applications.
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

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="font-bold text-slate-900">Create a draft batch</h3>
          <p className="mt-1 text-sm text-slate-500">
            Choose jobs already tracked in your application pipeline.
          </p>

          <form onSubmit={createBatch} className="mt-4 space-y-4">
            <label className="block text-sm font-medium text-slate-700">
              Batch name
              <input
                required
                minLength={1}
                maxLength={150}
                value={batchName}
                onChange={(event) => setBatchName(event.target.value)}
                placeholder="e.g. Backend roles — November"
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-violet-400"
              />
            </label>

            <div className="max-h-72 space-y-2 overflow-y-auto">
              {jobs.length === 0 && (
                <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">
                  No tracked jobs yet. Save jobs to your application pipeline first.
                </p>
              )}

              {jobs.map((job) => {
                const tracked = applications.find((item) => item.job_id === job.id);

                return (
                  <label key={job.id} className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-100 p-3 hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={selectedJobIds.includes(job.id)}
                      onChange={(event) => {
                        setSelectedJobIds((current) =>
                          event.target.checked
                            ? [...current, job.id]
                            : current.filter((id) => id !== job.id),
                        );
                      }}
                      className="mt-1 accent-violet-600"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-slate-800">{job.title}</span>
                      <span className="block text-xs text-slate-500">{job.company}</span>
                      <span className="block text-xs text-slate-400">Current status: {tracked?.status ?? "tracked"}</span>
                    </span>
                  </label>
                );
              })}
            </div>

            <button
              type="submit"
              disabled={saving || selectedJobIds.length === 0 || !batchName.trim()}
              className="w-full rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Saving..." : `Create draft (${selectedJobIds.length} selected)`}
            </button>
          </form>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="font-bold text-slate-900">Your batches</h3>

          {batches.length === 0 ? (
            <p className="mt-3 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
              No batches yet. Create a draft to begin reviewing jobs.
            </p>
          ) : (
            <div className="mt-3 space-y-2">
              {batches.map((batch) => (
                <button
                  key={batch.id}
                  type="button"
                  onClick={() => setActiveBatchId(batch.id)}
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
                    {batch.items.filter((item) => item.selected).length} of {batch.items.length} selected
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>

      {activeBatch && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="text-lg font-bold text-slate-900">{activeBatch.name}</h3>
              <p className="mt-1 text-sm text-slate-500">
                {activeBatch.items.filter((item) => item.selected).length} selected of {activeBatch.items.length} jobs
              </p>
            </div>

            {activeBatch.status === "draft" ? (
              <button
                type="button"
                onClick={() => void approveBatch()}
                disabled={saving || !activeBatch.items.some((item) => item.selected)}
                className="rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Approve selected jobs
              </button>
            ) : (
              <span className="text-sm font-semibold text-emerald-700">
                Approved {activeBatch.approved_at ? new Date(activeBatch.approved_at).toLocaleString() : ""}
              </span>
            )}
          </div>

          <div className="mt-4 space-y-2">
            {activeBatch.items.map((item) => (
              <label key={item.id} className="flex items-start gap-3 rounded-xl border border-slate-100 p-3">
                <input
                  type="checkbox"
                  checked={item.selected}
                  disabled={saving || activeBatch.status !== "draft"}
                  onChange={(event) => void toggleItem(item, event.target.checked)}
                  className="mt-1 accent-violet-600"
                />
                <span className="min-w-0 flex-1">
                  <span className="block font-semibold text-slate-800">{item.job.title}</span>
                  <span className="block text-sm text-slate-500">{item.job.company}</span>
                  <span className="block text-xs text-slate-400">{item.job.location || "Location not specified"}</span>
                </span>
                {item.selected && (
                  <span className="text-xs font-semibold text-violet-700">Selected</span>
                )}
              </label>
            ))}
          </div>

          <p className="mt-4 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-600">
            Approval is a review decision only. It does not send applications,
            contact employers, or change the status of jobs in your application pipeline.
          </p>
        </section>
      )}
    </section>
  );
}
