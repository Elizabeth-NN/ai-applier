"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";

type Job = {
  id: number;
  title: string;
  company: string;
  location: string | null;
};

type ApplicationStatus =
  | "saved"
  | "applied"
  | "interview"
  | "rejected"
  | "offer";

type Application = {
  id: number;
  job_id: number;
  status: ApplicationStatus;
  notes: string | null;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
};

const statuses: ApplicationStatus[] = [
  "saved",
  "applied",
  "interview",
  "offer",
  "rejected",
];

const statusLabels: Record<ApplicationStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
};

export default function ApplicationTracker() {
  const { isLoaded, isSignedIn, getToken } = useAuth();

  const [jobs, setJobs] = useState<Job[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false);

  async function apiRequest<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const token = await getToken();

    if (!token) {
      throw new Error("Your Clerk session token is unavailable. Please sign in again.");
    }

    const apiUrl = process.env.NEXT_PUBLIC_API_URL;

    if (!apiUrl) {
      throw new Error("NEXT_PUBLIC_API_URL is not configured.");
    }

    const response = await fetch(`${apiUrl}${path}`, {
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
        data?.detail ?? `Backend request failed (${response.status}).`,
      );
    }

    return data as T;
  }

  async function loadData() {
    setLoading(true);
    setError("");
    setNotice("");

    try {
      const [jobResults, applicationResults] = await Promise.all([
        apiRequest<Job[]>("/api/jobs?limit=100"),
        apiRequest<Application[]>("/api/applications?limit=100"),
      ]);

      setJobs(jobResults);
      setApplications(applicationResults);
      setLoaded(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load your applications.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function saveJob(jobId: number) {
    setBusyId(jobId);
    setError("");
    setNotice("");

    try {
      const created = await apiRequest<Application>("/api/applications", {
        method: "POST",
        body: JSON.stringify({ job_id: jobId, notes: null }),
      });

      setApplications((current) => [created, ...current]);
      setNotice("Job saved to your application tracker.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not save this job.",
      );
    } finally {
      setBusyId(null);
    }
  }

  async function changeStatus(
    application: Application,
    nextStatus: ApplicationStatus,
  ) {
    setBusyId(application.id);
    setError("");
    setNotice("");

    try {
      const updated = await apiRequest<Application>(
        `/api/applications/${application.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ status: nextStatus }),
        },
      );

      setApplications((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      setNotice(`Application status changed to ${statusLabels[nextStatus]}.`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not update the status.",
      );
    } finally {
      setBusyId(null);
    }
  }

  if (!isLoaded) {
    return <p className="text-sm text-slate-500">Loading authentication…</p>;
  }

  if (!isSignedIn) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-5">
        Sign in to manage your applications.
      </section>
    );
  }

  return (
    <section className="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-slate-900">
            My applications
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Saved to your account through the backend.
          </p>
        </div>

        <button
          type="button"
          onClick={loadData}
          disabled={loading}
          className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          {loading ? "Loading…" : loaded ? "Refresh" : "Load applications"}
        </button>
      </div>

      {error && (
        <p
          role="alert"
          className="break-words rounded-lg bg-red-50 p-3 text-sm text-red-700"
        >
          {error}
        </p>
      )}

      {notice && (
        <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">
          {notice}
        </p>
      )}

      {loaded && (
        <>
          <div>
            <h3 className="mb-3 font-semibold text-slate-800">
              Available jobs
            </h3>

            {jobs.length === 0 ? (
              <p className="text-sm text-slate-500">
                No jobs are available yet. Add jobs through the backend first.
              </p>
            ) : (
              <div className="space-y-3">
                {jobs.map((job) => {
                  const alreadySaved = applications.some(
                    (application) => application.job_id === job.id,
                  );

                  return (
                    <article
                      key={job.id}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-100 p-4"
                    >
                      <div className="min-w-0">
                        <h4 className="font-semibold text-slate-900">
                          {job.title}
                        </h4>
                        <p className="mt-1 text-sm text-slate-600">
                          {job.company}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          {job.location || "Location not specified"}
                        </p>
                      </div>

                      <button
                        type="button"
                        disabled={alreadySaved || busyId === job.id}
                        onClick={() => saveJob(job.id)}
                        className="rounded-lg border border-violet-200 px-3 py-2 text-sm font-semibold text-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {alreadySaved
                          ? "Already saved"
                          : busyId === job.id
                            ? "Saving…"
                            : "Save job"}
                      </button>
                    </article>
                  );
                })}
              </div>
            )}
          </div>

          <div>
            <h3 className="mb-3 font-semibold text-slate-800">
              Your tracked applications ({applications.length})
            </h3>

            {applications.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-200 p-5 text-sm text-slate-500">
                You have no tracked applications yet. Save a job above to get started.
              </p>
            ) : (
              <div className="space-y-3">
                {applications.map((application) => {
                  const job = jobs.find(
                    (item) => item.id === application.job_id,
                  );

                  return (
                    <article
                      key={application.id}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-100 p-4"
                    >
                      <div className="min-w-0">
                        <h4 className="font-semibold text-slate-900">
                          {job?.title ?? `Job #${application.job_id}`}
                        </h4>
                        <p className="mt-1 text-sm text-slate-600">
                          {job?.company ?? "Company unavailable"}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          Added{" "}
                          {new Date(application.created_at).toLocaleDateString()}
                        </p>
                      </div>

                      <label className="flex items-center gap-2 text-sm">
                        <span className="text-slate-500">Status</span>
                        <select
                          aria-label={`Status for ${job?.title ?? `job ${application.job_id}`}`}
                          value={application.status}
                          disabled={busyId === application.id}
                          onChange={(event) =>
                            changeStatus(
                              application,
                              event.target.value as ApplicationStatus,
                            )
                          }
                          className="max-w-40 rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-800 disabled:opacity-60"
                        >
                          {statuses.map((status) => (
                            <option key={status} value={status}>
                              {statusLabels[status]}
                            </option>
                          ))}
                        </select>
                      </label>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}
