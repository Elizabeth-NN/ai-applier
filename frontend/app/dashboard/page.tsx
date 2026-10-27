"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  SquaresFour,
  Lightning,
  Files,
  Briefcase,
  ChartPieSlice,
  GearSix,
  MagnifyingGlass,
  Bell,
  Plus,
  ArrowUpRight,
  MapPin,
  Clock,
  Sparkle,
  TrendUp,
  Binoculars,
  PaperPlaneTilt,
  ChatsCircle,
  CheckCircle,
  CaretRight,

  List,
  Kanban,
  X,
} from "@phosphor-icons/react";
import Navbar from "@/components/Navbar";
import BackendAuthCheck from "@/components/BackendAuthCheck";
import ApplicationBatches from "@/components/ApplicationBatches";
import CoverLetterDrafts from "@/components/CoverLetterDrafts";
import MyDocuments from "@/components/MyDocuments";
import Insights from "@/components/Insights";

type ApiJob = {
  id: number;
  company: string;
  title: string;
  location: string | null;
  created_at: string;
  remote_type: string | null;
  eligible_countries: string[] | null;
  eligibility_status: string;
  eligibility_evidence_url: string | null;
  eligibility_evidence: string | null;
  eligibility_verified_at: string | null;
  eligibility_verified_by: string | null;
  listing_status: string;
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

type Job = {
  id: number;
  company: string;
  title: string;
  location: string;
  createdAt: string;
  color: string;
  letter: string;
  applicationId: number | null;
  apiStatus: ApiApplication["status"] | null;
  status: "Available" | "Saved" | "Applied" | "Interview" | "Rejected" | "Offer";
  relevanceScore?: number;
  matchedRoleFamilies?: string[];
  relevanceReasons?: string[];
};

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
  const [evidence, setEvidence] = useState(
    job.eligibility_evidence ?? "",
  );
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

const navItems = [
  { label: "Dashboard", icon: SquaresFour },
  { label: "Job Matches", icon: Lightning, badge: "3" },
  { label: "My Documents", icon: Files },
  { label: "Applications", icon: Briefcase },
  { label: "Application Batches", icon: CheckCircle },
  { label: "Cover Letter Drafts", icon: Files },
  { label: "Insights", icon: ChartPieSlice },
];

const columns = [
  { name: "Saved", color: "text-slate-500", dot: "bg-slate-400" },
  { name: "Applied", color: "text-violet-600", dot: "bg-violet-500" },
  { name: "Interview", color: "text-amber-600", dot: "bg-amber-500" },
  { name: "Offer", color: "text-emerald-600", dot: "bg-emerald-500" },
] as const;

export default function DashboardPage() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [activePage, setActivePage] = useState("Dashboard");
  const [draftToOpenId, setDraftToOpenId] = useState<number | null>(null);
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [remoteType, setRemoteType] = useState("");
  const [eligibilityStatus, setEligibilityStatus] = useState("");
  const [listingStatus, setListingStatus] = useState("");
  const [jobPage, setJobPage] = useState(1);
  const [jobTotal, setJobTotal] = useState(0);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsRefreshKey, setJobsRefreshKey] = useState(0);
  const pageSize = 20;
  const [view, setView] = useState<"board" | "list">("board");
  const [apiJobs, setApiJobs] = useState<ApiJob[]>([]);
  const [applications, setApplications] = useState<ApiApplication[]>([]);
  const [trackedApiJobs, setTrackedApiJobs] = useState<ApiJob[]>([]);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [savingJobId, setSavingJobId] = useState<number | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [isImportingJobicy, setIsImportingJobicy] = useState(false);
  const [showJobForm, setShowJobForm] = useState(false);
  const [creatingJob, setCreatingJob] = useState(false);
  const [jobFormError, setJobFormError] = useState("");
  const [jobForm, setJobForm] = useState({
    title: "",
    company: "",
    location: "",
    employment_type: "",
    source_url: "",
    description: "",
  });

  const dashboardLoading = !isLoaded || (isSignedIn === true && loading);
  const dashboardError = !isLoaded
    ? ""
    : !isSignedIn
      ? "Sign in to load your jobs and applications."
      : error;

  useEffect(() => {
    if (!isLoaded) return;

    if (!isSignedIn) return;

    let cancelled = false;

    async function loadData() {
      setLoading(true);
      setError("");

      try {
        const token = await getToken();
        if (!token) {
          throw new Error("No Clerk session token is available.");
        }

        const [loadedApplications, hasAdminAccess] = await Promise.all([
          apiRequest<ApiApplication[]>("/api/applications?limit=100", token),
          apiRequest<{ is_admin: boolean }>("/api/admin/status", token)
            .then((result) => result.is_admin)
            .catch(() => false),
        ]);

        if (!cancelled) {
          setApplications(loadedApplications);
          setIsAdmin(hasAdminAccess);
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

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search.trim());
    }, 300);

    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

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
          skip: String((jobPage - 1) * pageSize),
          limit: String(pageSize),
        });

        if (remoteType) {
          params.set("remote_type", remoteType);
        }

        if (eligibilityStatus) {
          params.set("eligibility_status", eligibilityStatus);
        }

        if (listingStatus) {
          params.set("listing_status", listingStatus);
        }

        const result = await apiRequest<{
          items: ApiJob[];
          total: number;
          skip: number;
          limit: number;
        }>(`/api/jobs/search?${params.toString()}`, token);

        if (!cancelled) {
          setApiJobs(result.items);
          setJobTotal(result.total);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load jobs.",
          );
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
    debouncedSearch,
    jobPage,
    jobsRefreshKey,
    remoteType,
    eligibilityStatus,
    listingStatus,
  ]);

  const jobs = useMemo<Job[]>(
    () =>
      apiJobs.map((job, index) => {
        const application = applications.find(
          (item) => item.job_id === job.id,
        );

        return {
          id: job.id,
          company: job.company,
          title: job.title,
          location: job.location || "Location not specified",
          createdAt: new Date(job.created_at).toLocaleDateString(),
          color: companyColors[index % companyColors.length],
          letter: job.company.trim().charAt(0).toUpperCase() || "J",
          applicationId: application?.id ?? null,
          apiStatus: application?.status ?? null,
          status: application ? statusLabels[application.status] : "Available",
          relevanceScore: job.relevance_score,
          matchedRoleFamilies: job.matched_role_families,
          relevanceReasons: job.relevance_reasons,
        };
      }),
    [apiJobs, applications],
  );

  const filteredJobs = jobs;

  const totalPages = Math.max(1, Math.ceil(jobTotal / pageSize));
  const firstResult = jobTotal === 0 ? 0 : (jobPage - 1) * pageSize + 1;
  const lastResult = Math.min(jobPage * pageSize, jobTotal);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

    let cancelled = false;

    async function loadTrackedJobs() {
      try {
        const token = await getToken();

        if (!token) {
          throw new Error("No Clerk session token is available.");
        }

        const jobIds = [...new Set(applications.map((item) => item.job_id))];

        const loadedJobs = await Promise.all(
          jobIds.map((jobId) =>
            apiRequest<ApiJob>(`/api/jobs/${jobId}`, token),
          ),
        );

        if (!cancelled) {
          setTrackedApiJobs(loadedJobs);
        }
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
  }, [isLoaded, isSignedIn, getToken, applications]);

  const trackedJobs = useMemo<Job[]>(
    () =>
      trackedApiJobs.flatMap((job, index) => {
        const application = applications.find(
          (item) => item.job_id === job.id,
        );

        if (!application) return [];

        return [{
          id: job.id,
          company: job.company,
          title: job.title,
          location: job.location || "Location not specified",
          createdAt: new Date(job.created_at).toLocaleDateString(),
          color: companyColors[index % companyColors.length],
          letter: job.company.trim().charAt(0).toUpperCase() || "J",
          applicationId: application.id,
          apiStatus: application.status,
          status: statusLabels[application.status],
        }];
      }),
    [trackedApiJobs, applications],
  );

  const stats = [
    {
      label: "Available jobs",
      value: String(jobTotal),
      delta: "Jobs in search results",
      icon: Binoculars,
      style: "bg-indigo-50 text-indigo-600",
    },
    {
      label: "Applications",
      value: String(applications.length),
      delta: "Your tracked jobs",
      icon: PaperPlaneTilt,
      style: "bg-violet-50 text-violet-600",
    },
    {
      label: "Interviews",
      value: String(applications.filter((app) => app.status === "interview").length),
      delta: "Recorded interviews",
      icon: ChatsCircle,
      style: "bg-amber-50 text-amber-600",
    },
    {
      label: "Offers",
      value: String(applications.filter((app) => app.status === "offer").length),
      delta: "Recorded offers",
      icon: ChartPieSlice,
      style: "bg-emerald-50 text-emerald-600",
    },
  ];

  const [activity, setActivity] = useState<
    { day: string; count: number; height: number }[]
  >([]);

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
          height: day.count === 0 ? 0 : Math.max(8, (day.count / maximum) * 100),
        })),
      );
    });

    return () => window.cancelAnimationFrame(frame);
  }, [applications]);

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
      setNotice(`Application status changed to ${statusLabels[nextStatus]}.`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not update application.",
      );
    }
  }

  async function saveJob(jobId: number) {
    if (savingJobId !== null) return;

    const job = apiJobs.find((item) => item.id === jobId);
    if (!job) return;

    const existing = applications.find((item) => item.job_id === jobId);

    if (existing) {
      if (existing.status === "saved") {
        await changeStatus(existing.id, "applied");
      } else {
        setNotice(`This job is already tracked as ${statusLabels[existing.status]}.`);
      }
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
      setNotice("Job saved to your application pipeline.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not save this job.",
      );
    } finally {
      setSavingJobId(null);
    }
  }

  async function importJobicy() {
    if (isImportingJobicy) return;

    setIsImportingJobicy(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();
      if (!token) {
        throw new Error("Your session has expired. Please sign in again.");
      }

      const result = await apiRequest<{
        fetched: number;
        inserted: number;
        updated: number;
      }>("/api/jobs/ingest/jobicy", token, {
        method: "POST",
      });

      setJobPage(1);
      setJobsRefreshKey((current) => current + 1);
      setNotice(
        `Jobicy import complete: ${result.fetched} fetched, ` +
        `${result.inserted} inserted, ${result.updated} updated.`,
      );
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not import Jobicy jobs.",
      );
    } finally {
      setIsImportingJobicy(false);
    }
  }

  async function createJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
      setJobForm({
        title: "",
        company: "",
        location: "",
        employment_type: "",
        source_url: "",
        description: "",
      });
      setShowJobForm(false);
      setActivePage("Dashboard");
      setNotice("Job added successfully.");
    } catch (err) {
      setJobFormError(
        err instanceof Error ? err.message : "Could not create the job.",
      );
    } finally {
      setCreatingJob(false);
    }
  }

  function startApplication() {
    setActivePage("Job Matches");
    setNotice("Choose a job to save to your application pipeline.");
  }

  return (
    <>
    <Navbar />
    <div className="min-h-dvh pt-[68px]">
      <div className="flex min-h-[calc(100dvh-68px)]">
        <aside className="hidden w-64 shrink-0 flex-col bg-[#101323] text-white lg:sticky lg:top-[68px] lg:flex lg:h-[calc(100dvh-68px)] lg:overflow-y-auto">
          {/* <div className="flex items-center gap-3 px-6 py-7">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500">
              <Robot size={23} weight="fill" />
            </div>
            <div>
              <p className="text-lg font-extrabold tracking-tight">
                ai-applier
              </p>
              <p className="text-[10px] tracking-[0.18em] text-slate-400 uppercase">
                Career workspace
              </p>
            </div>
          </div> */}

          <div className="mx-4 mb-7 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-violet-500/20 text-sm font-bold text-violet-200">
                JD
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">Your profile</p>
                <p className="mt-1 text-xs text-slate-400">Free workspace</p>
              </div>
            </div>
          </div>

          <p className="px-6 pb-3 text-[10px] font-bold tracking-[0.18em] text-slate-500 uppercase">
            Workspace
          </p>

          <nav className="flex-1 space-y-1 px-3">
            {navItems.map(({ label, icon: Icon, badge }) => (
              <button
                key={label}
                onClick={() => setActivePage(label)}
                className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-sm transition ${
                  activePage === label
                    ? "sidebar-active font-semibold"
                    : "text-slate-400 hover:bg-white/5 hover:text-white"
                }`}
              >
                <Icon size={20} weight="duotone" />
                <span className="flex-1">{label}</span>
                {badge && (
                  <span className="rounded-md bg-violet-500/20 px-2 py-0.5 text-[10px] font-bold text-violet-300">
                    {badge}
                  </span>
                )}
              </button>
            ))}
          </nav>

          <div className="m-4 rounded-2xl border border-white/10 bg-gradient-to-br from-violet-500/15 to-transparent p-4">
            <div className="mb-3 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              <span className="text-xs font-semibold text-slate-200">
                AI workspace ready
              </span>
            </div>
            <p className="text-xs leading-relaxed text-slate-400">
              Connect your profile to get personalized job recommendations.
            </p>
            <button
              onClick={() => setActivePage("Settings")}
              className="mt-4 flex items-center gap-2 text-xs font-bold text-violet-300 hover:text-white"
            >
              <GearSix size={16} />
              Configure preferences
            </button>
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col">
          <div className="px-5 pt-5 sm:px-8 lg:px-10">
            <BackendAuthCheck />
          </div>
          <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200/70 bg-white px-5 py-4 sm:px-8 sm:py-5 lg:px-10">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-violet-600">
                  YOUR JOB SEARCH
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">
                  {dashboardLoading ? "Loading" : dashboardError ? "Connection issue" : "Live data"}
                </span>
              </div>
              <h1 className="mt-2 text-xl font-extrabold tracking-tight text-slate-900 sm:text-2xl">
                {activePage === "Dashboard"
                  ? "Your career dashboard"
                  : activePage}
              </h1>
              <p className="mt-1 hidden text-sm text-slate-500 sm:block">
                Your next opportunity starts here.
              </p>
            </div>

            <div className="flex w-full items-center gap-2 sm:w-auto sm:gap-3">
{activePage === "Job Matches" && (
              <label className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 focus-within:border-violet-300 sm:w-60 sm:flex-none">
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
                  placeholder="Search jobs..."
                  aria-label="Search jobs"
                  className="w-full min-w-0 bg-transparent text-base outline-none placeholder:text-slate-400 sm:text-sm"
                />
                {search && (
                  <button
                    onClick={() => setSearch("")}
                    aria-label="Clear search"
                    className="text-slate-400 hover:text-slate-700"
                  >
                    <X size={15} />
                  </button>
                )}
              </label>
              )}

              <button
                aria-label="Notifications"
                title="Notifications"
                onClick={() =>
                  setNotice("You are all caught up on notifications.")
                }
                className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
              >
                <Bell size={19} />
                <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-violet-500 ring-2 ring-white" />
              </button>

              {isAdmin && (
                <button
                  type="button"
                  onClick={importJobicy}
                  disabled={isImportingJobicy}
                  className="flex shrink-0 items-center gap-2 rounded-xl border border-emerald-200 bg-white px-3 py-2.5 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-60 sm:px-4"
                >
                  <span>
                    {isImportingJobicy ? "Importing jobs..." : "Import Jobicy jobs"}
                  </span>
                </button>
              )}

              {isAdmin && (
                <button
                  onClick={() => {
                    setShowJobForm((visible) => !visible);
                    setJobFormError("");
                  }}
                  aria-expanded={showJobForm}
                  className="flex shrink-0 items-center gap-2 rounded-xl border border-violet-200 bg-white px-3 py-2.5 text-sm font-semibold text-violet-700 transition hover:bg-violet-50 sm:px-4"
                >
                  <Plus size={18} />
                  <span>{showJobForm ? "Close form" : "Add job"}</span>
                </button>
              )}

              <button
                onClick={startApplication}
                className="flex shrink-0 items-center gap-2 rounded-xl bg-violet-600 px-3 py-2.5 text-sm font-semibold text-white shadow-sm shadow-violet-200 transition hover:bg-violet-700 sm:px-4"
              >
                <Plus size={18} />
                <span className="hidden sm:inline">New application</span>
                <span className="sm:hidden">New</span>
              </button>
            </div>
          </header>

          {notice && (
            <div
              role="status"
              className="mx-5 mt-4 flex items-center justify-between gap-3 rounded-xl border border-violet-100 bg-violet-50 px-4 py-3 text-sm text-violet-800 sm:mx-8 lg:mx-10"
            >
              <span className="min-w-0">{notice}</span>
              <button
                onClick={() => setNotice("")}
                aria-label="Dismiss notification"
                className="shrink-0"
              >
                <X size={16} />
              </button>
            </div>
          )}

          {dashboardError && (
            <div role="alert" className="mx-5 mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 sm:mx-8 lg:mx-10">
              {dashboardError}
            </div>
          )}

          {dashboardLoading && (
            <p role="status" className="px-5 pt-4 text-sm text-slate-500 sm:px-8 lg:px-10">
              Loading jobs and applications…
            </p>
          )}

          <div className="space-y-8 p-5 pb-24 sm:p-8 sm:pb-24 lg:p-10">
            {showJobForm && isAdmin && (
              <section className="rounded-2xl border border-violet-200 bg-white p-5 shadow-sm sm:p-7">
                <div className="mb-5">
                  <h2 className="text-lg font-bold text-slate-900">Add a job listing</h2>
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
                        onChange={(event) => setJobForm((current) => ({ ...current, title: event.target.value }))}
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
                        onChange={(event) => setJobForm((current) => ({ ...current, company: event.target.value }))}
                        className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                        placeholder="Company name"
                      />
                    </label>

                    <label className="block text-sm font-medium text-slate-700">
                      Location
                      <input
                        maxLength={255}
                        value={jobForm.location}
                        onChange={(event) => setJobForm((current) => ({ ...current, location: event.target.value }))}
                        className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                        placeholder="e.g. Remote or Nairobi, Kenya"
                      />
                    </label>

                    <label className="block text-sm font-medium text-slate-700">
                      Employment type
                      <select
                        value={jobForm.employment_type}
                        onChange={(event) => setJobForm((current) => ({ ...current, employment_type: event.target.value }))}
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
                        onChange={(event) => setJobForm((current) => ({ ...current, source_url: event.target.value }))}
                        className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                        placeholder="https://company.com/careers/job"
                      />
                    </label>

                    <label className="block text-sm font-medium text-slate-700 sm:col-span-2">
                      Description
                      <textarea
                        rows={5}
                        value={jobForm.description}
                        onChange={(event) => setJobForm((current) => ({ ...current, description: event.target.value }))}
                        className="mt-1.5 w-full resize-y rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100"
                        placeholder="Responsibilities, requirements, qualifications, and application instructions..."
                      />
                    </label>
                  </div>

                  {jobFormError && (
                    <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-sm text-red-700">
                      {jobFormError}
                    </p>
                  )}

                  <div className="flex flex-wrap justify-end gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        setShowJobForm(false);
                        setJobFormError("");
                      }}
                      disabled={creatingJob}
                      className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                    >
                      Cancel
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
            )}

            {activePage !== "Dashboard" &&
              activePage !== "Job Matches" &&
              activePage !== "Applications" &&
              activePage !== "Application Batches" &&
              activePage !== "Cover Letter Drafts" &&
              activePage !== "My Documents" &&
              activePage !== "Insights" && (
                <section className="rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
                  <Sparkle size={28} className="mb-4 text-violet-600" />
                  <h2 className="text-lg font-bold">{activePage}</h2>
                  <p className="mt-2 max-w-lg text-sm leading-6 text-slate-500">
                    This workspace section is planned but not connected yet.
                    Your dashboard and job-matching interactions are available
                    to explore.
                  </p>
                  <button
                    onClick={() => setActivePage("Dashboard")}
                    className="mt-5 text-sm font-bold text-violet-600 hover:text-violet-800"
                  >
                    Back to dashboard
                  </button>
                </section>
              )}

            {activePage === "Application Batches" && <ApplicationBatches />}
            {activePage === "Cover Letter Drafts" && (
              <CoverLetterDrafts initialDraftId={draftToOpenId} />
            )}
            {activePage === "My Documents" && (
              <MyDocuments
                onOpenEditor={(draftId) => {
                  setDraftToOpenId(draftId ?? null);
                  setActivePage("Cover Letter Drafts");
                }}
              />
            )}

            {activePage === "Insights" && <Insights />}

            {activePage === "Dashboard" && (
              <>
                <section className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
                  {stats.map(({ label, value, delta, icon: Icon, style }) => (
                    <article
                      key={label}
                      className="stat-card min-w-0 rounded-2xl border border-slate-200/80 bg-white p-4 sm:p-6"
                    >
                      <div className="flex items-center justify-between">
                        <div
                          className={`flex h-10 w-10 items-center justify-center rounded-xl sm:h-11 sm:w-11 ${style}`}
                        >
                          <Icon size={22} weight="duotone" />
                        </div>
                        <ArrowUpRight size={18} className="text-slate-300" />
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
                    </article>
                  ))}
                </section>
              </>
            )}

            {(activePage === "Dashboard" ||
              activePage === "Job Matches") && (
              <section className={`grid grid-cols-1 gap-6 ${activePage === "Dashboard" ? "xl:grid-cols-1" : "xl:grid-cols-3"}`}>
                  {activePage === "Job Matches" && (
                  <div className="space-y-4 xl:col-span-2">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900">
                          <Sparkle
                            size={21}
                            weight="fill"
                            className="text-violet-600"
                          />
                          Available jobs
                        </h2>
                        <p className="mt-1 text-sm text-slate-500">
                          Opportunities selected for your profile
                        </p>
                      </div>
                      <button
                        onClick={() => setActivePage("Job Matches")}
                        className="flex items-center gap-1 text-sm font-bold text-violet-600 hover:text-violet-800"
                      >
                        All matches <CaretRight size={16} />
                      </button>
                    </div>
                    <div className="grid grid-cols-1 gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-3">
                      <label className="space-y-1.5">
                        <span className="text-xs font-semibold text-slate-600">
                          Work arrangement
                        </span>
                        <select
                          value={remoteType}
                          onChange={(event) => {
                            setRemoteType(event.target.value);
                            setJobPage(1);
                          }}
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
                          Kenya eligibility
                        </span>
                        <select
                          value={eligibilityStatus}
                          onChange={(event) => {
                            setEligibilityStatus(event.target.value);
                            setJobPage(1);
                          }}
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
                          onChange={(event) => {
                            setListingStatus(event.target.value);
                            setJobPage(1);
                          }}
                          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm"
                        >
                          <option value="">All listing statuses</option>
                          <option value="active">Active</option>
                          <option value="closed">Closed</option>
                          <option value="unknown">Unverified</option>
                        </select>
                      </label>

                      {(remoteType || eligibilityStatus || listingStatus || search) && (
                        <button
                          type="button"
                          onClick={() => {
                            setRemoteType("");
                            setEligibilityStatus("");
                            setListingStatus("");
                            setSearch("");
                            setJobPage(1);
                          }}
                          className="text-left text-sm font-semibold text-violet-600 hover:text-violet-800 sm:col-span-3"
                        >
                          Clear all filters
                        </button>
                      )}
                    </div>

                    <div className="space-y-3">
                      {filteredJobs.length === 0 && (
                        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center">
                          <MagnifyingGlass
                            size={28}
                            className="mx-auto text-slate-400"
                          />
                          <p className="mt-3 font-semibold text-slate-800">
                            No matching jobs
                          </p>
                          <p className="mt-1 text-sm text-slate-500">
                            Try another title or company.
                          </p>
                        </div>
                      )}

                      {filteredJobs.map((job) => (
                        <article
                          key={job.id}
                          className="rounded-2xl border border-slate-200/80 bg-white p-4 transition hover:border-violet-200 sm:p-5"
                        >
                          <div className="flex flex-wrap items-start gap-3">
                            <div
                              className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-lg font-extrabold ${job.color}`}
                            >
                              {job.letter}
                            </div>

                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="font-bold text-slate-900">
                                  {job.title}
                                </h3>
                                <span
                                  className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${
                                    job.applicationId !== null
                                      ? "bg-emerald-50 text-emerald-700"
                                      : "bg-slate-100 text-slate-600"
                                  }`}
                                >
                                  {job.applicationId !== null
                                    ? job.status
                                    : "Available"}
                                </span>
                              </div>
                              <p className="mt-1 text-sm text-slate-600">
                                {job.company}
                              </p>

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

                                  {job.matchedRoleFamilies &&
                                    job.matchedRoleFamilies.length > 0 && (
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

                                  {job.relevanceReasons &&
                                    job.relevanceReasons.length > 0 && (
                                      <ul className="mt-2 space-y-1 text-xs text-slate-600">
                                        {job.relevanceReasons.map((reason, index) => (
                                          <li key={`${index}-${reason}`}>
                                            {reason}
                                          </li>
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
                                  {job.createdAt}
                                </span>
                              </div>
                            </div>

                            <button
                              onClick={() => saveJob(job.id)}
                              disabled={
                                savingJobId === job.id ||
                                (job.applicationId !== null && job.apiStatus !== "saved")
                              }
                              className={`flex w-full items-center justify-center gap-1.5 rounded-xl px-3 py-2.5 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:py-2 ${
                                job.applicationId !== null && job.apiStatus !== "saved"
                                  ? "bg-emerald-50 text-emerald-700"
                                  : "bg-violet-600 text-white hover:bg-violet-700"
                              }`}
                            >
                              {job.applicationId !== null && job.apiStatus !== "saved" ? (
                                <CheckCircle size={15} />
                              ) : (
                                <PaperPlaneTilt size={15} />
                              )}
                              {savingJobId === job.id
                                ? "Saving…"
                                : job.apiStatus === "saved"
                                  ? "Mark applied"
                                  : job.applicationId !== null
                                    ? job.status
                                    : "Save job"}
                            </button>
                          </div>

                          <EligibilityVerificationPanel
                            job={
                              apiJobs.find((item) => item.id === job.id)!
                            }
                            isAdmin={isAdmin}
                            onUpdated={(updated) => {
                              setApiJobs((current) =>
                                current.map((item) =>
                                  item.id === updated.id ? updated : item,
                                ),
                              );
                              setTrackedApiJobs((current) =>
                                current.map((item) =>
                                  item.id === updated.id ? updated : item,
                                ),
                              );
                            }}
                          />
                        </article>
                      ))}
                    </div>

                    <div className="flex flex-col gap-3 border-t border-slate-200 pt-4 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-sm text-slate-500" aria-live="polite">
                        {jobsLoading
                          ? "Searching jobs..."
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
                          onClick={() => setJobPage((page) => Math.min(totalPages, page + 1))}
                          disabled={jobsLoading || jobPage >= totalPages}
                          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  </div>
                  )}

                  {activePage === "Dashboard" && (
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
                            className={`w-full rounded-t-md transition-opacity hover:opacity-70 ${
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
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-xs text-slate-400">
                            Applications tracked
                          </p>
                          <p className="mt-2 text-2xl font-extrabold">{applications.length}</p>
                        </div>
                        <div className="rounded-xl bg-emerald-500/10 p-3 text-emerald-400">
                          <TrendUp size={23} />
                        </div>
                      </div>
                    </div>

                    <button
                      onClick={() => setActivePage("Insights")}
                      className="mt-6 flex items-center justify-center gap-2 rounded-xl border border-white/10 py-3 text-sm font-semibold text-slate-200 transition hover:bg-white/5"
                    >
                      View insights <ArrowUpRight size={17} />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setJobPage(1);
                        setActivePage("Job Matches");
                      }}
                      className="mt-3 flex items-center justify-center gap-2 rounded-xl bg-violet-600 py-3 text-sm font-semibold text-white transition hover:bg-violet-700"
                    >
                      All matches <CaretRight size={17} />
                    </button>
                  </article>
                  )}
              </section>
            )}

            {activePage === "Applications" && (
              <section className="space-y-4 pb-5">
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <div>
                    <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900">
                      <Briefcase size={21} className="text-violet-600" />
                      Application pipeline
                    </h2>
                    <p className="mt-1 text-sm text-slate-500">
                      Keep track of every opportunity in one place.
                    </p>
                  </div>

                  <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-1">
                    <button
                      onClick={() => setView("board")}
                      className={`flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold ${
                        view === "board"
                          ? "bg-slate-100 text-slate-900"
                          : "text-slate-500 hover:text-slate-900"
                      }`}
                    >
                      <Kanban size={16} /> Board
                    </button>
                    <button
                      onClick={() => setView("list")}
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

                {view === "board" ? (
                  <div className="custom-scrollbar -mx-5 flex snap-x snap-mandatory gap-4 overflow-x-auto px-5 pb-4 sm:mx-0 sm:snap-none sm:px-0">
                    {columns.map((column) => {
                      const columnJobs = trackedJobs.filter(
                        (job) => job.status === column.name,
                      );

                      return (
                        <div
                          key={column.name}
                          className="kanban-column w-[80%] shrink-0 snap-start space-y-3 sm:w-auto sm:flex-1"
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
                            <button
                              title={`Add ${column.name.toLowerCase()} application`}
                              aria-label={`Add ${column.name.toLowerCase()} application`}
                              onClick={startApplication}
                              className="flex h-9 w-9 items-center justify-center text-slate-400 hover:text-violet-600"
                            >
                              <Plus size={19} />
                            </button>
                          </div>

                          {columnJobs.length === 0 ? (
                            <div className="rounded-2xl border border-dashed border-slate-200 bg-white/60 p-5 text-center text-xs text-slate-400">
                              No applications here yet
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
                            Action
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

            <footer className="border-t border-slate-200 py-5 text-xs text-slate-400">
              AI Applier · Your job search, organized. Jobs and application
              statuses are loaded from your backend.
            </footer>
          </div>
        </main>
      </div>

      {mobileMoreOpen && (
        <div className="fixed inset-x-3 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-40 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl lg:hidden">
          {[
            { label: "Application Batches", icon: CheckCircle },
            { label: "Cover Letter Drafts", icon: Files },
            { label: "Insights", icon: ChartPieSlice },
          ].map(({ label, icon: Icon }) => (
            <button
              key={label}
              type="button"
              onClick={() => {
                setActivePage(label);
                setMobileMoreOpen(false);
              }}
              className={`flex w-full items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium ${
                activePage === label
                  ? "bg-violet-50 text-violet-700"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              <Icon size={20} />
              {label}
            </button>
          ))}
        </div>
      )}

      <nav
        aria-label="Mobile dashboard navigation"
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        {[
          { label: "Home", page: "Dashboard", icon: SquaresFour },
          { label: "Jobs", page: "Job Matches", icon: Lightning },
          { label: "Applications", page: "Applications", icon: Briefcase },
          { label: "Documents", page: "My Documents", icon: Files },
          { label: "More", page: "More", icon: List },
        ].map(({ label, page, icon: Icon }) => {
          const active =
            page === "More"
              ? mobileMoreOpen ||
                ["Application Batches", "Cover Letter Drafts", "Insights"].includes(activePage)
              : activePage === page;

          return (
            <button
              key={label}
              type="button"
              onClick={() => {
                if (page === "More") {
                  setMobileMoreOpen((open) => !open);
                } else {
                  setActivePage(page);
                  setMobileMoreOpen(false);
                }
              }}
              aria-current={page !== "More" && active ? "page" : undefined}
              aria-expanded={page === "More" ? mobileMoreOpen : undefined}
              className={`flex min-w-0 min-h-14 flex-col items-center justify-center gap-1 px-0.5 text-[10px] font-semibold ${
                active ? "text-violet-600" : "text-slate-500"
              }`}
            >
              <Icon size={22} weight={active ? "fill" : "duotone"} />
              <span className="whitespace-nowrap">{label}</span>
            </button>
          );
        })}
      </nav>
    </div>
    </>
  );
}