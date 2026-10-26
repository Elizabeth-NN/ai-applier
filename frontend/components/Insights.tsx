"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  ChartPieSlice,
  Briefcase,
  PaperPlaneTilt,
  ChatsCircle,
  CheckCircle,
  XCircle,
  TrendUp,
  ArrowClockwise,
} from "@phosphor-icons/react";

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
  applied_at: string | null;
  created_at: string;
  updated_at: string;
};

const statusConfig: {
  key: ApplicationStatus;
  label: string;
  color: string;
  bar: string;
}[] = [
  { key: "saved", label: "Saved", color: "text-slate-600", bar: "bg-slate-400" },
  { key: "applied", label: "Applied", color: "text-violet-700", bar: "bg-violet-500" },
  { key: "interview", label: "Interviews", color: "text-amber-700", bar: "bg-amber-500" },
  { key: "offer", label: "Offers", color: "text-emerald-700", bar: "bg-emerald-500" },
  { key: "rejected", label: "Rejected", color: "text-rose-700", bar: "bg-rose-500" },
];

async function fetchApplications(
  token: string,
  skip: number,
): Promise<Application[]> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;

  if (!apiUrl) {
    throw new Error("NEXT_PUBLIC_API_URL is not configured.");
  }

  const response = await fetch(
    `${apiUrl.replace(/\/$/, "")}/api/applications?skip=${skip}&limit=100`,
    {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    },
  );

  const data: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      data &&
      typeof data === "object" &&
      "detail" in data &&
      typeof data.detail === "string"
        ? data.detail
        : `Could not load applications (${response.status}).`;

    throw new Error(detail);
  }

  if (!Array.isArray(data)) {
    throw new Error("The applications API returned an unexpected response.");
  }

  return data as Application[];
}

function formatDate(date: Date): string {
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function startOfDay(date: Date): Date {
  const result = new Date(date);
  result.setHours(0, 0, 0, 0);
  return result;
}

export default function Insights() {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activityRange, setActivityRange] = useState<7 | 30 | 90>(7);

  const loadData = useCallback(async () => {
    const token = await getToken();

    if (!token) {
      throw new Error("No authenticated session token is available.");
    }

    const allApplications: Application[] = [];
    let skip = 0;

    while (true) {
      const page = await fetchApplications(token, skip);
      allApplications.push(...page);

      if (page.length < 100) break;

      skip += page.length;
    }

    setApplications(allApplications);
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
              : "Could not load your insights.",
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

  const total = applications.length;
  const count = (status: ApplicationStatus) =>
    applications.filter((application) => application.status === status).length;

  const applied = count("applied");
  const interviews = count("interview");
  const offers = count("offer");
  const rejected = count("rejected");

  const today = startOfDay(new Date());
  const currentPeriodStart = new Date(today);
  currentPeriodStart.setDate(today.getDate() - (activityRange - 1));

  const nextDay = new Date(today);
  nextDay.setDate(today.getDate() + 1);

  const previousPeriodStart = new Date(currentPeriodStart);
  previousPeriodStart.setDate(
    currentPeriodStart.getDate() - activityRange,
  );

  const currentPeriodCount = applications.filter((application) => {
    const created = new Date(application.created_at);
    return created >= currentPeriodStart && created < nextDay;
  }).length;

  const previousPeriodCount = applications.filter((application) => {
    const created = new Date(application.created_at);
    return created >= previousPeriodStart && created < currentPeriodStart;
  }).length;

  const periodChange = currentPeriodCount - previousPeriodCount;
  const periodChangePercent =
    previousPeriodCount > 0
      ? Math.round((periodChange / previousPeriodCount) * 100)
      : null;

  const activity = Array.from({ length: 7 }, (_, index) => {
    const today = startOfDay(new Date());
    const rangeStart = new Date(today);
    rangeStart.setDate(today.getDate() - (activityRange - 1));

    const bucketStart = new Date(rangeStart);
    bucketStart.setDate(
      rangeStart.getDate() + Math.floor((index * activityRange) / 7),
    );

    const bucketEnd = new Date(rangeStart);
    bucketEnd.setDate(
      rangeStart.getDate() + Math.floor(((index + 1) * activityRange) / 7),
    );

    const value = applications.filter((application) => {
      const created = new Date(application.created_at);
      return created >= bucketStart && created < bucketEnd;
    }).length;

    const lastDay = new Date(bucketEnd);
    lastDay.setDate(lastDay.getDate() - 1);

    return {
      date: bucketStart,
      label:
        activityRange === 7
          ? formatDate(bucketStart)
          : `${formatDate(bucketStart)}–${formatDate(lastDay)}`,
      value,
    };
  });

  const maxActivity = Math.max(1, ...activity.map((day) => day.value));

  if (!isLoaded || (isSignedIn && loading)) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-8">
        <p className="text-sm text-slate-500">Loading your insights...</p>
      </section>
    );
  }

  if (!isSignedIn) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-8">
        <h2 className="text-lg font-bold text-slate-900">Sign in required</h2>
        <p className="mt-2 text-sm text-slate-500">
          Sign in to view your application insights.
        </p>
      </section>
    );
  }

  if (loading) {
    return (
      <section className="rounded-2xl border border-slate-200 bg-white p-8">
        <p className="text-sm text-slate-500">Loading your insights...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-2xl border border-rose-200 bg-white p-6">
        <h2 className="font-bold text-rose-700">Insights could not be loaded</h2>
        <p className="mt-2 text-sm text-slate-600">{error}</p>
        <button
          onClick={() => {
            setLoading(true);
            void loadData()
              .then(() => setError(""))
              .catch((err: unknown) =>
                setError(
                  err instanceof Error ? err.message : "Could not load insights.",
                ),
              )
              .finally(() => setLoading(false));
          }}
          className="mt-4 inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700"
        >
          <ArrowClockwise size={16} /> Try again
        </button>
      </section>
    );
  }

  const cards = [
    {
      label: "Total tracked",
      value: total,
      icon: Briefcase,
      iconStyle: "bg-slate-100 text-slate-700",
    },
    {
      label: "Applied",
      value: applied,
      icon: PaperPlaneTilt,
      iconStyle: "bg-violet-100 text-violet-700",
    },
    {
      label: "Interviews",
      value: interviews,
      icon: ChatsCircle,
      iconStyle: "bg-amber-100 text-amber-700",
    },
    {
      label: "Offers",
      value: offers,
      icon: CheckCircle,
      iconStyle: "bg-emerald-100 text-emerald-700",
    },
  ];

  return (
    <div className="space-y-6 pb-8">
      <header>
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-violet-100 p-3 text-violet-700">
            <ChartPieSlice size={24} />
          </div>
          <div>
            <h2 className="text-xl font-extrabold text-slate-900">
              Application insights
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              A snapshot of your job search based on your tracked applications.
            </p>
          </div>
        </div>
      </header>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ label, value, icon: Icon, iconStyle }) => (
          <article
            key={label}
            className="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-500">{label}</p>
              <span className={`rounded-xl p-2 ${iconStyle}`}>
                <Icon size={20} />
              </span>
            </div>
            <p className="mt-4 text-3xl font-extrabold text-slate-900">
              {value}
            </p>
          </article>
        ))}
      </section>

      <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <article className="rounded-2xl border border-slate-200 bg-white p-6">
          <h3 className="font-bold text-slate-900">Application pipeline</h3>
          <p className="mt-1 text-sm text-slate-500">
            Current status of your tracked opportunities.
          </p>

          {total === 0 ? (
            <p className="mt-6 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
              No applications tracked yet. Save a job or add an application to
              start building your insights.
            </p>
          ) : (
            <div className="mt-6 space-y-5">
              {statusConfig.map((status) => {
                const value = count(status.key);
                const percentage = (value / total) * 100;

                return (
                  <div key={status.key}>
                    <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                      <span className={`font-semibold ${status.color}`}>
                        {status.label}
                      </span>
                      <span className="tabular-nums text-slate-600">
                        {value} <span className="text-slate-400">({Math.round(percentage)}%)</span>
                      </span>
                    </div>
                    <div
                      className="h-2.5 overflow-hidden rounded-full bg-slate-100"
                      role="progressbar"
                      aria-label={`${status.label} applications`}
                      aria-valuemin={0}
                      aria-valuemax={total}
                      aria-valuenow={value}
                    >
                      <div
                        className={`h-full rounded-full ${status.bar}`}
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </article>

        <article className="rounded-2xl border border-slate-200 bg-white p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="font-bold text-slate-900">Recent activity</h3>
              <p className="mt-1 text-sm text-slate-500">
                Applications created over the last {activityRange} days.
              </p>
            </div>
            <TrendUp size={22} className="text-violet-600" />
          </div>

          <div
            className="mt-5 inline-flex rounded-lg bg-slate-100 p-1"
            aria-label="Activity date range"
          >
            {([7, 30, 90] as const).map((range) => (
              <button
                key={range}
                type="button"
                onClick={() => setActivityRange(range)}
                aria-pressed={activityRange === range}
                className={`rounded-md px-3 py-2 text-sm font-semibold transition ${
                  activityRange === range
                    ? "bg-white text-violet-700 shadow-sm"
                    : "text-slate-500 hover:text-slate-900"
                }`}
              >
                {range} days
              </button>
            ))}
          </div>

          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-slate-600">
                  Applications created this period
                </p>
                <p className="mt-1 text-2xl font-extrabold text-slate-900">
                  {currentPeriodCount}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-slate-500">
                  Previous {activityRange} days: {previousPeriodCount}
                </p>
                <p
                  className={`mt-1 text-sm font-bold ${
                    periodChange > 0
                      ? "text-emerald-700"
                      : periodChange < 0
                        ? "text-rose-700"
                        : "text-slate-600"
                  }`}
                >
                  {periodChange > 0 ? "+" : ""}
                  {periodChange} applications
                  {periodChangePercent !== null
                    ? ` (${periodChangePercent > 0 ? "+" : ""}${periodChangePercent}%)`
                    : previousPeriodCount === 0 && currentPeriodCount > 0
                      ? " (new activity)"
                      : ""}
                </p>
              </div>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              Compared with the {activityRange} days immediately before this period.
              {previousPeriodCount === 0 && currentPeriodCount === 0
                ? " There was no activity in either period."
                : ""}
            </p>
          </div>

          <div className="mt-6 grid grid-cols-7 items-end gap-2">
            {activity.map((day) => (
              <div key={day.date.toISOString()} className="flex min-w-0 flex-col items-center gap-2">
                <span className="text-xs font-semibold tabular-nums text-slate-600">
                  {day.value}
                </span>
                <div className="flex h-32 w-full items-end rounded-lg bg-slate-50 p-1">
                  <div
                    className="w-full rounded-md bg-violet-500 transition-all"
                    style={{
                      height: `${day.value === 0 ? 3 : Math.max(8, (day.value / maxActivity) * 100)}%`,
                    }}
                  />
                </div>
                <span className="text-center text-[10px] text-slate-500 sm:text-xs">
                  {day.label}
                </span>
              </div>
            ))}
          </div>

          <p className="mt-5 text-xs leading-5 text-slate-500">
            Activity is based on when an application record was created, not
            necessarily when you submitted it to an employer.
          </p>
        </article>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h3 className="font-bold text-slate-900">Outcome overview</h3>
        <p className="mt-1 text-sm text-slate-500">
          Review the outcomes recorded in your application tracker.
        </p>
        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="rounded-xl bg-amber-50 p-4">
            <p className="text-sm text-amber-800">Interviews</p>
            <p className="mt-2 text-2xl font-extrabold text-amber-900">
              {interviews}
            </p>
          </div>
          <div className="rounded-xl bg-emerald-50 p-4">
            <p className="text-sm text-emerald-800">Offers</p>
            <p className="mt-2 text-2xl font-extrabold text-emerald-900">
              {offers}
            </p>
          </div>
          <div className="rounded-xl bg-rose-50 p-4">
            <div className="flex items-center gap-2 text-sm text-rose-800">
              <XCircle size={16} /> Rejected
            </div>
            <p className="mt-2 text-2xl font-extrabold text-rose-900">
              {rejected}
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
