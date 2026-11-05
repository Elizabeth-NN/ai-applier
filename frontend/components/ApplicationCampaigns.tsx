"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";

type CampaignStatus =
  | "draft"
  | "active"
  | "paused"
  | "completed"
  | "archived";

type ApplicationCampaign = {
  id: number;
  name: string;
  target_applications: number;
  starts_on: string;
  deadline_on: string;
  status: CampaignStatus;
};

type CampaignProgress = {
  campaign_id: number;
  target_applications: number;
  submitted: number;
  remaining: number;
  percentage: number;
  days_remaining: number;
  required_per_week: number | null;
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

function localDateString(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function defaultDeadline(startDate: string): string {
  const date = new Date(`${startDate}T12:00:00`);
  date.setDate(date.getDate() + 56);
  return localDateString(date);
}

function formatDate(value: string): string {
  return new Date(`${value}T12:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

const statusStyles: Record<CampaignStatus, string> = {
  draft: "bg-slate-100 text-slate-700",
  active: "bg-emerald-100 text-emerald-700",
  paused: "bg-amber-100 text-amber-700",
  completed: "bg-blue-100 text-blue-700",
  archived: "bg-slate-100 text-slate-500",
};

export default function ApplicationCampaigns() {
  const { isLoaded, isSignedIn, getToken } = useAuth();

  const [campaigns, setCampaigns] = useState<ApplicationCampaign[]>([]);
  const [activeCampaignId, setActiveCampaignId] = useState<number | null>(null);
  const [progress, setProgress] = useState<CampaignProgress | null>(null);

  const [name, setName] = useState("");
  const [target, setTarget] = useState("500");
  const [startsOn, setStartsOn] = useState(() =>
    localDateString(new Date()),
  );
  const [deadlineOn, setDeadlineOn] = useState(() =>
    defaultDeadline(localDateString(new Date())),
  );

  const [loading, setLoading] = useState(true);
  const [loadingProgress, setLoadingProgress] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const activeCampaign =
    campaigns.find((campaign) => campaign.id === activeCampaignId) ?? null;

  const loadCampaigns = useCallback(async () => {
    const token = await getToken();

    if (!token) {
      throw new Error("Your session has expired. Please sign in again.");
    }

    const loaded = await apiRequest<ApplicationCampaign[]>(
      "/api/application-campaigns?limit=100",
      token,
    );

    setCampaigns(loaded);
    setActiveCampaignId((current) => {
      if (current !== null && loaded.some((item) => item.id === current)) {
        return current;
      }

      return loaded[0]?.id ?? null;
    });
  }, [getToken]);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");

      try {
        await loadCampaigns();
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load campaigns.",
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
  }, [isLoaded, isSignedIn, loadCampaigns]);

  useEffect(() => {
    if (!activeCampaignId || !isLoaded || !isSignedIn) {
      return;
    }

    let cancelled = false;

    async function loadProgress() {
      setLoadingProgress(true);
      setProgress(null);

      try {
        const token = await getToken();

        if (!token) {
          throw new Error("Please sign in again.");
        }

        const loaded = await apiRequest<CampaignProgress>(
          `/api/application-campaigns/${activeCampaignId}/progress`,
          token,
        );

        if (!cancelled) setProgress(loaded);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load campaign progress.",
          );
        }
      } finally {
        if (!cancelled) setLoadingProgress(false);
      }
    }

    void loadProgress();

    return () => {
      cancelled = true;
    };
  }, [activeCampaignId, getToken, isLoaded, isSignedIn]);

  async function createCampaign(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();

      if (!token) throw new Error("Please sign in again.");

      const created = await apiRequest<ApplicationCampaign>(
        "/api/application-campaigns",
        token,
        {
          method: "POST",
          body: JSON.stringify({
            name: name.trim(),
            target_applications: Number(target),
            starts_on: startsOn,
            deadline_on: deadlineOn,
          }),
        },
      );

      setCampaigns((current) => [created, ...current]);
      setActiveCampaignId(created.id);
      setName("");
      setNotice("Campaign created. You can now track confirmed submissions.");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not create the campaign.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function updateStatus(status: CampaignStatus) {
    if (!activeCampaign) return;

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const token = await getToken();

      if (!token) throw new Error("Please sign in again.");

      const updated = await apiRequest<ApplicationCampaign>(
        `/api/application-campaigns/${activeCampaign.id}`,
        token,
        {
          method: "PATCH",
          body: JSON.stringify({ status }),
        },
      );

      setCampaigns((current) =>
        current.map((item) => item.id === updated.id ? updated : item),
      );
      setNotice(`Campaign status updated to ${status}.`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not update campaign status.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (!isLoaded || (isSignedIn && loading)) {
    return <p className="text-sm text-slate-500">Loading campaigns...</p>;
  }

  if (!isSignedIn) {
    return <p className="text-sm text-slate-500">Sign in to manage campaigns.</p>;
  }

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Application Campaigns</h2>
        <p className="mt-1 text-sm text-slate-500">
          Set a job-search target and deadline, then track applications that
          have actually been confirmed as submitted.
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
          <h3 className="font-bold text-slate-900">Create a campaign</h3>
          <p className="mt-1 text-sm text-slate-500">
            Define the number of applications you want to submit and your timeframe.
          </p>

          <form onSubmit={createCampaign} className="mt-4 space-y-4">
            <label className="block text-sm font-medium text-slate-700">
              Campaign name
              <input
                required
                minLength={1}
                maxLength={150}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Remote junior software roles"
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-violet-400"
              />
            </label>

            <label className="block text-sm font-medium text-slate-700">
              Application target
              <input
                required
                type="number"
                min={1}
                step={1}
                value={target}
                onChange={(event) => setTarget(event.target.value)}
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-violet-400"
              />
            </label>

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block text-sm font-medium text-slate-700">
                Start date
                <input
                  required
                  type="date"
                  value={startsOn}
                  onChange={(event) => {
                    setStartsOn(event.target.value);
                    if (event.target.value) {
                      setDeadlineOn(defaultDeadline(event.target.value));
                    }
                  }}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-violet-400"
                />
              </label>

              <label className="block text-sm font-medium text-slate-700">
                Deadline
                <input
                  required
                  type="date"
                  min={startsOn}
                  value={deadlineOn}
                  onChange={(event) => setDeadlineOn(event.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-violet-400"
                />
              </label>
            </div>

            <p className="text-xs text-slate-400">
              The default deadline is eight weeks after the start date.
            </p>

            <button
              type="submit"
              disabled={
                saving ||
                !name.trim() ||
                !target ||
                Number(target) < 1 ||
                !startsOn ||
                !deadlineOn ||
                deadlineOn <= startsOn
              }
              className="w-full rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? "Creating..." : "Create campaign"}
            </button>
          </form>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h3 className="font-bold text-slate-900">Your campaigns</h3>

          {campaigns.length === 0 ? (
            <p className="mt-3 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
              No campaigns yet. Create one to start tracking your application target.
            </p>
          ) : (
            <div className="mt-3 space-y-2">
              {campaigns.map((campaign) => (
                <button
                  key={campaign.id}
                  type="button"
                  onClick={() => setActiveCampaignId(campaign.id)}
                  className={`w-full rounded-xl border p-3 text-left ${
                    activeCampaignId === campaign.id
                      ? "border-violet-300 bg-violet-50"
                      : "border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="font-semibold text-slate-800">{campaign.name}</span>
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${statusStyles[campaign.status]}`}>
                      {campaign.status}
                    </span>
                  </span>
                  <span className="mt-1 block text-xs text-slate-500">
                    Target: {campaign.target_applications} applications
                  </span>
                  <span className="mt-1 block text-xs text-slate-400">
                    {formatDate(campaign.starts_on)} – {formatDate(campaign.deadline_on)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>

      {activeCampaign && (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h3 className="text-lg font-bold text-slate-900">
                {activeCampaign.name}
              </h3>
              <p className="mt-1 text-sm text-slate-500">
                {formatDate(activeCampaign.starts_on)} – {formatDate(activeCampaign.deadline_on)}
              </p>
            </div>

            <label className="text-sm font-medium text-slate-600">
              Campaign status
              <select
                value={activeCampaign.status}
                disabled={saving}
                onChange={(event) => updateStatus(event.target.value as CampaignStatus)}
                className="ml-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm capitalize outline-none focus:border-violet-400"
              >
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
                <option value="completed">Completed</option>
                <option value="archived">Archived</option>
              </select>
            </label>
          </div>

          {loadingProgress ? (
            <p className="mt-6 text-sm text-slate-500">Loading campaign progress...</p>
          ) : progress?.campaign_id === activeCampaign.id ? (
            <>
              <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs font-medium text-slate-500">Confirmed submitted</p>
                  <p className="mt-1 text-2xl font-bold text-slate-900">
                    {progress.submitted}
                    <span className="text-sm font-medium text-slate-400"> / {progress.target_applications}</span>
                  </p>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs font-medium text-slate-500">Remaining</p>
                  <p className="mt-1 text-2xl font-bold text-slate-900">{progress.remaining}</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs font-medium text-slate-500">Days remaining</p>
                  <p className="mt-1 text-2xl font-bold text-slate-900">{progress.days_remaining}</p>
                </div>
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs font-medium text-slate-500">Required weekly pace</p>
                  <p className="mt-1 text-2xl font-bold text-slate-900">
                    {progress.required_per_week === null
                      ? "—"
                      : progress.required_per_week}
                  </p>
                </div>
              </div>

              <div className="mt-6">
                <div className="mb-2 flex justify-between text-sm">
                  <span className="font-medium text-slate-700">Campaign progress</span>
                  <span className="font-semibold text-violet-700">{progress.percentage}%</span>
                </div>
                <div
                  className="h-3 overflow-hidden rounded-full bg-slate-100"
                  role="progressbar"
                  aria-label="Campaign progress"
                  aria-valuenow={progress.percentage}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="h-full rounded-full bg-violet-600 transition-all"
                    style={{ width: `${progress.percentage}%` }}
                  />
                </div>
              </div>
            </>
          ) : (
            <p className="mt-6 text-sm text-slate-500">
              Campaign progress is not currently available.
            </p>
          )}

          <p className="mt-5 text-xs text-slate-400">
            Only executions confirmed as submitted count toward this target.
            Preparing or approving an application does not increase progress.
          </p>
        </section>
      )}
    </section>
  );
}
