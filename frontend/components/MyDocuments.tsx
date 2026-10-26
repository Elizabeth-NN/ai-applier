"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

type ApiApplication = {
  id: number;
  job_id: number;
  status: string;
  created_at: string;
};

type ApiJob = {
  id: number;
  title: string;
  company: string;
  location: string | null;
};

type CoverLetterDraft = {
  id: number;
  application_id: number;
  content: string;
  created_at: string;
  updated_at: string;
};

async function apiRequest<T>(path: string, token: string): Promise<T> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }

  const response = await fetch(
    `${apiUrl.replace(/\/$/, "")}${path}`,
    {
      headers: { Authorization: `Bearer ${token}` },
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

type MyDocumentsProps = {
  onOpenEditor: (draftId?: number) => void;
};

export default function MyDocuments({
  onOpenEditor,
}: MyDocumentsProps) {
  const { isLoaded, isSignedIn, getToken } = useAuth();

  const [applications, setApplications] = useState<ApiApplication[]>([]);
  const [jobs, setJobs] = useState<ApiJob[]>([]);
  const [drafts, setDrafts] = useState<CoverLetterDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isLoaded) return;

    if (!isSignedIn) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function loadDocuments() {
      setLoading(true);
      setError("");

      try {
        const token = await getToken();

        if (!token) {
          throw new Error("Your session has expired. Please sign in again.");
        }

        const [loadedApplications, loadedDrafts] = await Promise.all([
          apiRequest<ApiApplication[]>(
            "/api/applications?limit=100",
            token,
          ),
          apiRequest<CoverLetterDraft[]>(
            "/api/cover-letter-drafts?limit=100",
            token,
          ),
        ]);

        const jobIds = [
          ...new Set(loadedApplications.map((application) => application.job_id)),
        ];

        const loadedJobs = await Promise.all(
          jobIds.map((jobId) =>
            apiRequest<ApiJob>(`/api/jobs/${jobId}`, token),
          ),
        );

        if (!cancelled) {
          setApplications(loadedApplications);
          setDrafts(loadedDrafts);
          setJobs(loadedJobs);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load your documents.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadDocuments();

    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken]);

  if (!isLoaded || loading) {
    return (
      <p className="text-sm text-slate-500">Loading your documents...</p>
    );
  }

  if (!isSignedIn) {
    return (
      <p className="text-sm text-slate-500">
        Sign in to view your saved documents.
      </p>
    );
  }

  const applicationById = new Map(
    applications.map((application) => [application.id, application]),
  );
  const jobById = new Map(jobs.map((job) => [job.id, job]));

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-900">My Documents</h2>
          <p className="mt-1 text-sm leading-6 text-slate-500">
            Find your saved cover letters in one place. Review and edit each
            draft before using it in an application.
          </p>
        </div>

        <button
          type="button"
          onClick={() => onOpenEditor()}
          className="inline-flex shrink-0 items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700"
        >
          Open cover letter editor
        </button>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {!error && drafts.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center sm:p-12">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-violet-50 text-violet-700">
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              className="h-6 w-6"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M7 3.75h7l4 4v12.5H7a2 2 0 0 1-2-2v-12.5a2 2 0 0 1 2-2Z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M14 3.75v4h4M8.5 12h6M8.5 15.5h6"
              />
            </svg>
          </div>
          <h3 className="mt-4 font-semibold text-slate-900">
            Your document library is empty
          </h3>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
            Saved cover letters will appear here with their associated job
            details and last-updated dates.
          </p>
          <button
            type="button"
            onClick={() => onOpenEditor()}
            className="mt-5 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700"
          >
            Create your first cover letter
          </button>
        </div>
      )}

      {drafts.length > 0 && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500">
              {drafts.length} saved {drafts.length === 1 ? "document" : "documents"}
            </p>
            <p className="text-xs text-slate-400">
              Sorted by most recently updated
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {drafts.map((draft) => {
              const application = applicationById.get(draft.application_id);
              const job = application
                ? jobById.get(application.job_id)
                : undefined;

              return (
                <article
                  key={draft.id}
                  className="flex min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-5"
                >
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-violet-50 text-violet-700">
                      <svg
                        aria-hidden="true"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.7"
                        className="h-5 w-5"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M7 3.75h7l4 4v12.5H7a2 2 0 0 1-2-2v-12.5a2 2 0 0 1 2-2Z"
                        />
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M14 3.75v4h4M8.5 12h6M8.5 15.5h6"
                        />
                      </svg>
                    </div>

                    <div className="min-w-0 flex-1">
                      <h3 className="break-words font-semibold text-slate-900">
                        {job?.title ?? `Cover letter draft #${draft.id}`}
                      </h3>
                      <p className="mt-1 break-words text-sm text-slate-500">
                        {job?.company ?? "Job details unavailable"}
                      </p>
                    </div>
                  </div>

                  <p className="mt-4 line-clamp-4 min-h-20 whitespace-pre-wrap break-words text-sm leading-6 text-slate-600">
                    {draft.content.trim() || "This draft is empty."}
                  </p>

                  <div className="mt-4 border-t border-slate-100 pt-4">
                    <p className="text-xs text-slate-500">
                      Last updated
                    </p>
                    <p className="mt-1 text-xs text-slate-700">
                      {new Date(draft.updated_at).toLocaleString()}
                    </p>

                    <button
                      type="button"
                      onClick={() => onOpenEditor(draft.id)}
                      className="mt-4 w-full rounded-xl border border-violet-200 px-3 py-2.5 text-sm font-semibold text-violet-700 hover:bg-violet-50"
                    >
                      Open in editor
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}

      {applications.length === 0 && drafts.length === 0 && !error && (
        <p className="text-center text-xs text-slate-400">
          Track an application before creating a cover letter for it.
        </p>
      )}
    </section>
  );
}
