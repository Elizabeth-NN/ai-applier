"use client";

import { useMemo, useState } from "react";
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
  Robot,
  List,
  Kanban,
  X,
} from "@phosphor-icons/react";

type Job = {
  id: number;
  company: string;
  title: string;
  location: string;
  match: number;
  age: string;
  color: string;
  letter: string;
  status: "Saved" | "Applied" | "Interview" | "Offer";
};

const initialJobs: Job[] = [
  {
    id: 1,
    company: "Stripe",
    title: "Junior Software Engineer",
    location: "Remote",
    match: 96,
    age: "2 hours ago",
    color: "bg-indigo-50 text-indigo-700",
    letter: "S",
    status: "Saved",
  },
  {
    id: 2,
    company: "GitLab",
    title: "Associate Backend Engineer",
    location: "Remote · Global",
    match: 92,
    age: "5 hours ago",
    color: "bg-orange-50 text-orange-700",
    letter: "G",
    status: "Saved",
  },
  {
    id: 3,
    company: "Canva",
    title: "Graduate Software Developer",
    location: "Remote · Selected regions",
    match: 88,
    age: "Yesterday",
    color: "bg-teal-50 text-teal-700",
    letter: "C",
    status: "Saved",
  },
];

const navItems = [
  { label: "Dashboard", icon: SquaresFour },
  { label: "Job Matches", icon: Lightning, badge: "3" },
  { label: "My Documents", icon: Files },
  { label: "Applications", icon: Briefcase },
  { label: "Insights", icon: ChartPieSlice },
];

const stats = [
  {
    label: "Jobs matched",
    value: "128",
    delta: "This month",
    icon: Binoculars,
    style: "bg-indigo-50 text-indigo-600",
  },
  {
    label: "Applications",
    value: "24",
    delta: "6 pending review",
    icon: PaperPlaneTilt,
    style: "bg-violet-50 text-violet-600",
  },
  {
    label: "Interviews",
    value: "4",
    delta: "2 upcoming",
    icon: ChatsCircle,
    style: "bg-amber-50 text-amber-600",
  },
  {
    label: "Response rate",
    value: "16.7%",
    delta: "Based on demo data",
    icon: ChartPieSlice,
    style: "bg-emerald-50 text-emerald-600",
  },
];

const columns = [
  { name: "Saved", color: "text-slate-500", dot: "bg-slate-400" },
  { name: "Applied", color: "text-violet-600", dot: "bg-violet-500" },
  { name: "Interview", color: "text-amber-600", dot: "bg-amber-500" },
  { name: "Offer", color: "text-emerald-600", dot: "bg-emerald-500" },
] as const;

const activity = [
  { day: "Mon", height: 35 },
  { day: "Tue", height: 55 },
  { day: "Wed", height: 42 },
  { day: "Thu", height: 75 },
  { day: "Fri", height: 92 },
  { day: "Sat", height: 48 },
  { day: "Sun", height: 65 },
];

export default function DashboardPage() {
  const [activePage, setActivePage] = useState("Dashboard");
  const [search, setSearch] = useState("");
  const [view, setView] = useState<"board" | "list">("board");
  const [jobs, setJobs] = useState(initialJobs);
  const [notice, setNotice] = useState("");

  const filteredJobs = useMemo(() => {
    const term = search.trim().toLowerCase();

    return jobs.filter((job) =>
      `${job.title} ${job.company} ${job.location}`
        .toLowerCase()
        .includes(term),
    );
  }, [jobs, search]);

  function saveJob(jobId: number) {
    setJobs((current) =>
      current.map((job) =>
        job.id === jobId
          ? {
              ...job,
              status: job.status === "Saved" ? "Applied" : "Saved",
            }
          : job,
      ),
    );
    setNotice("Application status updated.");
    window.setTimeout(() => setNotice(""), 2500);
  }

  function startApplication() {
    setActivePage("Job Matches");
    setNotice("Choose a matching job to start your application.");
    window.setTimeout(() => setNotice(""), 3000);
  }

  return (
    <div className="min-h-dvh lg:h-dvh lg:overflow-hidden">
      <div className="flex min-h-dvh lg:h-full">
        <aside className="hidden w-64 shrink-0 flex-col bg-[#101323] text-white lg:flex">
          <div className="flex items-center gap-3 px-6 py-7">
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
          </div>

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

        <main className="flex min-w-0 flex-1 flex-col lg:h-full lg:overflow-hidden">
          <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200/70 bg-white px-5 py-4 sm:px-8 sm:py-5 lg:px-10">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-violet-600">
                  YOUR JOB SEARCH
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500">
                  Demo
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
              <label className="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 focus-within:border-violet-300 sm:w-60 sm:flex-none">
                <MagnifyingGlass
                  size={18}
                  className="shrink-0 text-slate-400"
                />
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
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

          <div className="custom-scrollbar flex-1 space-y-8 overflow-y-auto p-5 pb-24 sm:p-8 sm:pb-24 lg:p-10">
            {activePage !== "Dashboard" &&
              activePage !== "Job Matches" &&
              activePage !== "Applications" && (
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

            {(activePage === "Dashboard" ||
              activePage === "Applications") && (
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

                <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
                  <div className="space-y-4 xl:col-span-2">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h2 className="flex items-center gap-2 text-lg font-extrabold text-slate-900">
                          <Sparkle
                            size={21}
                            weight="fill"
                            className="text-violet-600"
                          />
                          AI job matches
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
                                    job.match >= 90
                                      ? "bg-emerald-50 text-emerald-700"
                                      : "bg-amber-50 text-amber-700"
                                  }`}
                                >
                                  {job.match}% match
                                </span>
                              </div>
                              <p className="mt-1 text-sm text-slate-600">
                                {job.company}
                              </p>
                              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
                                <span className="flex items-center gap-1.5">
                                  <MapPin size={14} />
                                  {job.location}
                                </span>
                                <span className="flex items-center gap-1.5">
                                  <Clock size={14} />
                                  {job.age}
                                </span>
                              </div>
                            </div>

                            <button
                              onClick={() => saveJob(job.id)}
                              className={`flex w-full items-center justify-center gap-1.5 rounded-xl px-3 py-2.5 text-xs font-bold transition sm:w-auto sm:py-2 ${
                                job.status === "Applied"
                                  ? "bg-emerald-50 text-emerald-700"
                                  : "bg-violet-600 text-white hover:bg-violet-700"
                              }`}
                            >
                              {job.status === "Applied" ? (
                                <CheckCircle size={15} />
                              ) : (
                                <PaperPlaneTilt size={15} />
                              )}
                              {job.status === "Applied" ? "Applied" : "Apply"}
                            </button>
                          </div>
                        </article>
                      ))}
                    </div>
                  </div>

                  <article className="flex flex-col rounded-2xl bg-[#111426] p-5 text-white sm:p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-semibold text-slate-300">
                          Weekly activity
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          Illustrative demo data
                        </p>
                      </div>
                      <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/15 text-violet-300">
                        <TrendUp size={21} />
                      </div>
                    </div>

                    <div className="mt-8 flex h-36 items-end gap-2 sm:gap-3">
                      {activity.map(({ day, height }, index) => (
                        <div
                          key={day}
                          className="flex h-full flex-1 flex-col items-center justify-end gap-3"
                        >
                          <div
                            title={`${day}: ${height}% illustration`}
                            className={`w-full rounded-t-md transition-opacity hover:opacity-70 ${
                              index === 4
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
                          <p className="mt-2 text-2xl font-extrabold">24</p>
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
                  </article>
                </section>
              </>
            )}

            {(activePage === "Dashboard" ||
              activePage === "Applications" ||
              activePage === "Job Matches") && (
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
                      const columnJobs = filteredJobs.filter(
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
                                  <button
                                    onClick={() => saveJob(job.id)}
                                    title="Move between Saved and Applied"
                                    className="shrink-0 text-xs font-bold text-violet-600 hover:text-violet-800"
                                  >
                                    {job.status === "Saved"
                                      ? "Mark applied"
                                      : "Undo"}
                                  </button>
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
                            Match
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
                        {filteredJobs.map((job) => (
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
                            <td className="px-4 py-4 font-semibold text-emerald-700 sm:px-5">
                              {job.match}%
                            </td>
                            <td className="px-4 py-4 text-slate-600 sm:px-5">
                              {job.status}
                            </td>
                            <td className="px-4 py-4 sm:px-5">
                              <button
                                onClick={() => saveJob(job.id)}
                                className="font-semibold whitespace-nowrap text-violet-600"
                              >
                                {job.status === "Saved"
                                  ? "Mark applied"
                                  : "Undo"}
                              </button>
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
              AI Applier · Your job search, organized. All current dashboard
              metrics and job listings are illustrative demo data.
            </footer>
          </div>
        </main>
      </div>

      <nav
        aria-label="Primary"
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-slate-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        {navItems.map(({ label, icon: Icon, badge }) => {
          const active = activePage === label;

          return (
            <button
              key={label}
              onClick={() => setActivePage(label)}
              aria-current={active ? "page" : undefined}
              className={`relative flex min-h-14 flex-col items-center justify-center gap-1 px-1 text-[10px] font-semibold ${
                active ? "text-violet-600" : "text-slate-500"
              }`}
            >
              <Icon size={22} weight={active ? "fill" : "duotone"} />
              <span className="max-w-full truncate">
                {label.replace("My ", "").replace("Job ", "")}
              </span>
              {badge && (
                <span className="absolute right-[calc(50%-20px)] top-2 h-2 w-2 rounded-full bg-violet-500" />
              )}
            </button>
          );
        })}
      </nav>
    </div>
  );
}