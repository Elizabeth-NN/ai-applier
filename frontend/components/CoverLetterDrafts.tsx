"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

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

type ApiResume = {
  id: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

type CoverLetterDraft = {
  id: number;
  application_id: number;
  content: string;
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
    throw new Error(
      data && typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status}).`,
    );
  }

  return data as T;
}

type CoverLetterDraftsProps = {
  initialDraftId?: number | null;
};

export default function CoverLetterDrafts({
  initialDraftId = null,
}: CoverLetterDraftsProps) {
  const { isLoaded, isSignedIn, getToken } = useAuth();

  const [applications, setApplications] = useState<ApiApplication[]>([]);
  const [jobs, setJobs] = useState<ApiJob[]>([]);
  const [resumes, setResumes] = useState<ApiResume[]>([]);
  const [drafts, setDrafts] = useState<CoverLetterDraft[]>([]);
  const [selectedApplicationId, setSelectedApplicationId] = useState("");
  const [selectedResumeId, setSelectedResumeId] = useState("");
  const [generating, setGenerating] = useState(false);
  const [selectedDraftId, setSelectedDraftId] = useState<number | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedContent, setSavedContent] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadData = useCallback(async () => {
    const token = await getToken();

    if (!token) {
      throw new Error("Your session has expired. Please sign in again.");
    }

    const [loadedApplications, loadedDrafts, loadedResumes] = await Promise.all([
      apiRequest<ApiApplication[]>("/api/applications?limit=100", token),
      apiRequest<CoverLetterDraft[]>("/api/cover-letter-drafts?limit=100", token),
      apiRequest<ApiResume[]>("/api/resumes", token),
    ]);

    const jobIds = [...new Set(loadedApplications.map((item) => item.job_id))];

    const loadedJobs = await Promise.all(
      jobIds.map((jobId) =>
        apiRequest<ApiJob>(`/api/jobs/${jobId}`, token),
      ),
    );

    setApplications(loadedApplications);
    setJobs(loadedJobs);
    setResumes(loadedResumes);
    setDrafts(loadedDrafts);
    setSelectedResumeId((current) =>
      loadedResumes.some((resume) => String(resume.id) === current)
        ? current
        : loadedResumes[0]
          ? String(loadedResumes[0].id)
          : "",
    );

    // Prefer the exact draft selected from My Documents.
    const requestedDraft = initialDraftId === null
      ? undefined
      : loadedDrafts.find((draft) => draft.id === initialDraftId);

    // Otherwise keep the current application, or fall back to the first.
    const firstApplication = loadedApplications[0];
    const currentApplicationId = selectedApplicationId;
    const applicationStillExists = loadedApplications.some(
      (item) => String(item.id) === currentApplicationId,
    );
    const nextApplicationId = requestedDraft
      ? String(requestedDraft.application_id)
      : applicationStillExists
        ? currentApplicationId
        : firstApplication
          ? String(firstApplication.id)
          : "";

    setSelectedApplicationId(nextApplicationId);

    // Load the requested draft, or the latest draft for this application.
    const initialDraft = requestedDraft ?? loadedDrafts.find(
      (draft) => String(draft.application_id) === nextApplicationId,
    );

    setSelectedDraftId(initialDraft?.id ?? null);
    setContent(initialDraft?.content ?? "");
    setSavedContent(initialDraft?.content ?? null);
  }, [getToken, selectedApplicationId, initialDraftId]);

  useEffect(() => {
    if (!isLoaded) return;

    if (!isSignedIn) {
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
          setError(
            err instanceof Error
              ? err.message
              : "Could not load cover letter drafts.",
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

  const selectedApplication =
    applications.find(
      (item) => String(item.id) === selectedApplicationId,
    ) ?? null;

  const selectedJob = selectedApplication
    ? jobs.find((job) => job.id === selectedApplication.job_id) ?? null
    : null;

  const applicationDrafts = drafts.filter(
    (draft) => String(draft.application_id) === selectedApplicationId,
  );

  const selectedDraft =
    applicationDrafts.find((draft) => draft.id === selectedDraftId) ?? null;

  function selectApplication(applicationId: string) {
    setSelectedApplicationId(applicationId);

    const existingDraft = drafts.find(
      (draft) => String(draft.application_id) === applicationId,
    );

    setSelectedDraftId(existingDraft?.id ?? null);
    setContent(existingDraft?.content ?? "");
    setSavedContent(existingDraft?.content ?? null);
    setError("");
    setNotice("");
  }

  function selectDraft(draftId: string) {
    if (!draftId) {
      setSelectedDraftId(null);
      setContent("");
      setSavedContent(null);
    } else {
      const draft = drafts.find((item) => item.id === Number(draftId));

      if (draft) {
        setSelectedDraftId(draft.id);
        setContent(draft.content);
        setSavedContent(draft.content);
      }
    }

    setError("");
    setNotice("");
  }

  async function generateCoverLetter() {
    if (!selectedApplication) {
      setError("Select an application first.");
      return;
    }

    if (!selectedResumeId) {
      setError("Upload and select a resume first.");
      return;
    }

    setGenerating(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();

      if (!token) {
        throw new Error("Please sign in again.");
      }

      const result = await apiRequest<{ content: string }>(
        "/api/cover-letter-generation",
        token,
        {
          method: "POST",
          body: JSON.stringify({
            application_id: selectedApplication.id,
            resume_id: Number(selectedResumeId),
          }),
        },
      );

      // Keep existing saved drafts untouched; this becomes a new draft.
      setSelectedDraftId(null);
      setContent(result.content);
      setSavedContent(null);
      setNotice("AI draft generated. Review it carefully before saving.");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not generate a cover letter.",
      );
    } finally {
      setGenerating(false);
    }
  }

  async function saveDraft() {
    if (!selectedApplication) {
      setError("Select an application first.");
      return;
    }

    if (!content.trim()) {
      setError("Write some cover letter content before saving.");
      return;
    }

    if (content.length > 20000) {
      setError("Cover letter content must be 20,000 characters or fewer.");
      return;
    }

    setSaving(true);
    setError("");
    setNotice("");
    setSavedContent(null);

    try {
      const token = await getToken();

      if (!token) {
        throw new Error("Please sign in again.");
      }

      let savedDraft: CoverLetterDraft;

      if (selectedDraftId !== null) {
        savedDraft = await apiRequest<CoverLetterDraft>(
          `/api/cover-letter-drafts/${selectedDraftId}`,
          token,
          {
            method: "PATCH",
            body: JSON.stringify({ content }),
          },
        );

        setDrafts((current) =>
          current.map((draft) =>
            draft.id === savedDraft.id ? savedDraft : draft,
          ),
        );
        setSavedContent(savedDraft.content);
        setNotice("Cover letter draft saved.");
      } else {
        savedDraft = await apiRequest<CoverLetterDraft>(
          "/api/cover-letter-drafts",
          token,
          {
            method: "POST",
            body: JSON.stringify({
              application_id: selectedApplication.id,
              content,
            }),
          },
        );

        setDrafts((current) => [savedDraft, ...current]);
        setSelectedDraftId(savedDraft.id);
        setSavedContent(savedDraft.content);
        setNotice("Cover letter draft created and saved.");
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not save the draft.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (!isLoaded || (isSignedIn && loading)) {
    return (
      <p className="text-sm text-slate-500">
        Loading cover letter drafts...
      </p>
    );
  }

  if (!isSignedIn) {
    return (
      <p className="text-sm text-slate-500">
        Sign in to manage your cover letter drafts.
      </p>
    );
  }

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">
          Cover Letter Drafts
        </h2>
        <p className="mt-1 text-sm leading-6 text-slate-500">
          Prepare and save tailored cover letters for your tracked
          applications. Review each draft before using it.
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          {error}
        </p>
      )}

      {notice && (
        <p
          role="status"
          className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"
        >
          {notice}
        </p>
      )}

      {applications.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <h3 className="font-semibold text-slate-900">
            No tracked applications yet
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Save a job to your application tracker before creating a
            cover letter draft for it.
          </p>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <h3 className="font-bold text-slate-900">
              Choose an application
            </h3>

            <label className="mt-4 block text-sm font-medium text-slate-700">
              Tracked application
              <select
                value={selectedApplicationId}
                onChange={(event) =>
                  selectApplication(event.target.value)
                }
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 outline-none focus:border-violet-400"
              >
                {applications.map((application) => {
                  const job = jobs.find(
                    (item) => item.id === application.job_id,
                  );

                  return (
                    <option
                      key={application.id}
                      value={String(application.id)}
                    >
                      {job
                        ? `${job.title} — ${job.company}`
                        : `Application #${application.id}`}
                    </option>
                  );
                })}
              </select>
            </label>

            {selectedApplication && (
              <div className="mt-4 rounded-xl bg-slate-50 p-4">
                <p className="font-semibold text-slate-900">
                  {selectedJob?.title ?? "Tracked job"}
                </p>
                <p className="mt-1 text-sm text-slate-600">
                  {selectedJob?.company ?? `Job #${selectedApplication.job_id}`}
                </p>
                <p className="mt-2 text-xs text-slate-500">
                  Application status: {selectedApplication.status}
                </p>
              </div>
            )}

            <div className="mt-6">
              <h4 className="text-sm font-bold text-slate-900">
                Saved drafts
              </h4>

              {applicationDrafts.length === 0 ? (
                <p className="mt-2 rounded-xl bg-slate-50 p-3 text-sm text-slate-500">
                  No drafts for this application yet. Start writing
                  one in the editor.
                </p>
              ) : (
                <div className="mt-3 space-y-2">
                  {applicationDrafts.map((draft) => (
                    <button
                      key={draft.id}
                      type="button"
                      onClick={() => selectDraft(String(draft.id))}
                      className={`w-full rounded-xl border p-3 text-left ${
                        selectedDraftId === draft.id
                          ? "border-violet-300 bg-violet-50"
                          : "border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <span className="block text-sm font-semibold text-slate-800">
                        Draft #{draft.id}
                      </span>
                      <span className="mt-1 block text-xs text-slate-500">
                        Updated{" "}
                        {new Date(draft.updated_at).toLocaleString()}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {applicationDrafts.length > 0 && (
                <button
                  type="button"
                  onClick={() => selectDraft("")}
                  className="mt-3 text-sm font-semibold text-violet-600 hover:text-violet-800"
                >
                  Start another draft
                </button>
              )}
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-bold text-slate-900">
                  {selectedDraft ? `Edit draft #${selectedDraft.id}` : "Write a cover letter"}
                </h3>
                <p className="mt-1 text-sm text-slate-500">
                  Keep it specific, accurate, and relevant to the job.
                </p>
              </div>

              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                {content.length.toLocaleString()}/20,000 characters
              </span>
            </div>

            <div className="mt-5 rounded-xl border border-violet-100 bg-violet-50/50 p-4">
              <label className="block text-sm font-medium text-slate-700">
                Generate from resume
                <select
                  value={selectedResumeId}
                  onChange={(event) => setSelectedResumeId(event.target.value)}
                  disabled={generating || resumes.length === 0}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 outline-none focus:border-violet-400 disabled:opacity-60"
                >
                  {resumes.length === 0 ? (
                    <option value="">No resumes uploaded</option>
                  ) : (
                    resumes.map((resume) => (
                      <option key={resume.id} value={String(resume.id)}>
                        {resume.original_filename}
                      </option>
                    ))
                  )}
                </select>
              </label>

              {resumes.length === 0 ? (
                <p className="mt-2 text-sm text-slate-600">
                  Upload a PDF or DOCX resume in My Documents before generating.
                </p>
              ) : (
                <p className="mt-2 text-sm text-slate-600">
                  Uses the selected job description and resume. Generated text
                  is not saved until you choose to save it.
                </p>
              )}

              <button
                type="button"
                onClick={() => void generateCoverLetter()}
                disabled={
                  generating ||
                  !selectedApplication ||
                  !selectedResumeId ||
                  resumes.length === 0
                }
                className="mt-3 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {generating ? "Generating..." : "Generate with AI"}
              </button>
            </div>

            <label className="mt-5 block text-sm font-medium text-slate-700">
              Cover letter content
              <textarea
                value={content}
                onChange={(event) => {
                  setContent(event.target.value);
                  setNotice("");
                }}
                maxLength={20000}
                rows={18}
                placeholder={`Dear Hiring Manager,

I am writing to express my interest in the ${selectedJob?.title ?? "position"} role at ${selectedJob?.company ?? "your company"}.

Explain how your relevant skills and experience match the role. Include specific, truthful examples of your work and why you are interested in the opportunity.

Kind regards,`}
                className="mt-1.5 w-full resize-y rounded-xl border border-slate-200 px-3 py-3 leading-6 outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
              />
            </label>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-slate-500">
                Saving stores a draft only. It does not submit an application.
              </p>
              <button
                type="button"
                onClick={() => void saveDraft()}
                disabled={saving || !content.trim() || content.length > 20000}
                className="rounded-xl bg-violet-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {saving
                  ? "Saving..."
                  : savedContent === content && selectedDraft
                    ? "Saved"
                    : selectedDraft
                      ? "Save changes"
                      : "Create draft"}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
