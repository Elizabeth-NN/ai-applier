
"use client";

import { useState } from "react";
import {
  ArrowDownRight,
  ArrowRight,
  Briefcase,
  Check,
  CircleNotch,
  FileText,
  FunnelSimple,
  MagnifyingGlass,
  PaperPlaneTilt,
  RocketLaunch,
  Sparkle,
  Target,
  TrendUp,
} from "@phosphor-icons/react";

import Navbar from "@/components/Navbar";

const navigation = [
  { label: "Features", href: "#features" },
  { label: "How it works", href: "#how-it-works" },
  { label: "Pricing", href: "#pricing" },
] as const;

const features = [
  {
    Icon: MagnifyingGlass,
    number: "01",
    title: "Find relevant opportunities",
    description:
      "Organize your search around the roles, skills, locations and companies that matter to you.",
  },
  {
    Icon: FileText,
    number: "02",
    title: "Make every application count",
    description:
      "Use AI-assisted resume and cover letter improvements tailored to each opportunity.",
  },
  {
    Icon: Target,
    number: "03",
    title: "Stay on top of your search",
    description:
      "Keep applications, follow-ups and interview preparation organized in one place.",
  },
];

const steps = [
  {
    number: "01",
    title: "Set your direction",
    description:
      "Define your target roles, preferred locations and experience. Build a clear picture of your next move.",
  },
  {
    number: "02",
    title: "Prepare your applications",
    description:
      "Review relevant opportunities and use AI assistance to improve your application materials.",
  },
  {
    number: "03",
    title: "Track every next step",
    description:
      "Record application progress, plan follow-ups and prepare for conversations with employers.",
  },
];

const jobs = [
  {
    company: "Northstar Labs",
    role: "Software Engineer",
    type: "Full-time",
    initials: "N",
    color: "bg-violet-100 text-violet-700",
    status: "Applied",
    statusColor: "bg-blue-50 text-blue-700",
  },
  {
    company: "Meridian Tech",
    role: "Frontend Developer",
    type: "Remote",
    initials: "M",
    color: "bg-emerald-100 text-emerald-700",
    status: "Interview",
    statusColor: "bg-emerald-50 text-emerald-700",
  },
  {
    company: "Atlas Digital",
    role: "Junior Backend Developer",
    type: "Full-time",
    initials: "A",
    color: "bg-amber-100 text-amber-800",
    status: "In review",
    statusColor: "bg-amber-50 text-amber-800",
  },
] as const;

const plans = [
  {
    name: "Free",
    description: "Build an organized job-search routine.",
    monthly: 0,
    yearly: 0,
    features: [
      "Application tracking",
      "One resume profile",
      "Basic job-search organization",
    ],
    featured: false,
  },
  {
    name: "Pro",
    description: "More tools for an active job search.",
    monthly: 19,
    yearly: 15,
    features: [
      "Everything in Free",
      "AI-assisted application materials",
      "Advanced search organization",
      "Interview preparation tools",
    ],
    featured: true,
  },
  {
    name: "Teams",
    description: "Coordinate job-search support at scale.",
    monthly: null,
    yearly: null,
    features: [
      "Team-oriented workflows",
      "Centralized tracking",
      "Support for organizational needs",
    ],
    featured: false,
  },
] as const;

function Logo() {
  return (
    <a
      href="/"
      aria-label="AI Applier home"
      className="group inline-flex items-center gap-2.5"
    >
      <span className="grid size-10 place-items-center rounded-xl bg-violet text-white shadow-lg shadow-violet/20 transition-transform group-hover:-rotate-6">
        <RocketLaunch size={21} weight="fill" />
      </span>
      <span className="font-display text-xl font-extrabold tracking-tight">
        AI<span className="text-violet">Applier</span>
      </span>
    </a>
  );
}

export default function AIApplierLanding() {
  const [yearly, setYearly] = useState(true);

  return (
    <main className="min-h-screen overflow-hidden bg-paper text-ink">
      <Navbar />

      <Hero />

      <div className="border-y border-ink/[0.07] bg-white/70 px-6 py-5">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-center gap-x-3 gap-y-2 text-center text-sm text-ink/60">
          <span className="grid size-7 place-items-center rounded-full bg-violet/10 text-violet">
            <Check size={15} weight="bold" />
          </span>
          Built to help you organize your search, prepare applications and keep track of progress.
        </div>
      </div>

      <Features />

      <HowItWorks />

      <Pricing yearly={yearly} setYearly={setYearly} />

      <FinalCTA />

      <Footer />
    </main>
  );
}





function Hero() {
  return (
    <section className="relative px-5 pb-20 pt-32 sm:px-8 sm:pt-40 lg:pb-28 lg:pt-44">
      <div className="pointer-events-none absolute left-1/2 top-8 -z-0 size-[550px] -translate-x-1/2 rounded-full bg-violet/10 blur-[120px]" />

      <div className="relative mx-auto grid max-w-6xl items-center gap-16 lg:grid-cols-[0.92fr_1.08fr]">
        <div className="relative z-10">
          <div className="inline-flex items-center gap-2 rounded-full border border-violet/15 bg-white/80 px-3.5 py-2 text-xs font-bold text-violet shadow-sm">
            <Sparkle size={15} weight="fill" />
            A more organized way to job search
          </div>

          <h1 className="mt-7 max-w-2xl font-display text-5xl font-extrabold leading-[1.04] tracking-[-0.055em] sm:text-6xl lg:text-[68px]">
            Your next career move deserves{" "}
            <span className="relative whitespace-nowrap text-violet">
              a better plan.
              <svg
                aria-hidden="true"
                viewBox="0 0 300 12"
                className="absolute -bottom-2 left-0 w-full text-violet/30"
                fill="none"
              >
                <path
                  d="M3 8C76 2 190 2 297 7"
                  stroke="currentColor"
                  strokeWidth="5"
                  strokeLinecap="round"
                />
              </svg>
            </span>
          </h1>

          <p className="mt-7 max-w-xl text-base leading-8 text-ink/65 sm:text-lg">
            Find opportunities, improve your application materials with AI and
            manage your job search in one workspace. Spend less time juggling
            spreadsheets and more time preparing for what comes next.
          </p>

          <div className="mt-9 flex flex-wrap gap-3">
            <a
              href="/dashboard"
              className="inline-flex items-center gap-2.5 rounded-xl bg-violet px-6 py-4 text-sm font-bold text-white shadow-xl shadow-violet/25 transition-all hover:-translate-y-1 hover:shadow-2xl hover:shadow-violet/25"
            >
              Explore your workspace
              <ArrowRight size={17} weight="bold" />
            </a>
            <a
              href="#how-it-works"
              className="inline-flex items-center gap-2 rounded-xl border border-ink/10 bg-white/70 px-6 py-4 text-sm font-bold transition-colors hover:bg-white"
            >
              How it works <ArrowDownRight size={17} />
            </a>
          </div>

          <div className="mt-7 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs font-medium text-ink/55">
            <span className="inline-flex items-center gap-1.5">
              <Check size={14} weight="bold" className="text-violet" />
              Keep applications organized
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Check size={14} weight="bold" className="text-violet" />
              Stay in control
            </span>
          </div>
        </div>

        <ProductPreview />
      </div>
    </section>
  );
}

function ProductPreview() {
  return (
    <div className="relative mx-auto w-full max-w-[580px] lg:ml-auto">
      <div className="pointer-events-none absolute -inset-5 rounded-[32px] bg-gradient-to-br from-violet/15 via-transparent to-fuchsia-200/30 blur-2xl" />

      <div className="relative rounded-[25px] border border-white bg-white p-2.5 shadow-[0_28px_90px_-28px_rgba(64,43,120,0.3)] sm:p-3">
        <div className="overflow-hidden rounded-[19px] border border-ink/[0.06] bg-[#fbfaff]">
          <div className="flex items-center justify-between border-b border-ink/[0.07] bg-white px-4 py-4 sm:px-5">
            <div className="flex items-center gap-3">
              <span className="grid size-9 place-items-center rounded-xl bg-violet text-white">
                <Briefcase size={18} weight="fill" />
              </span>
              <div>
                <p className="text-sm font-extrabold">Application tracker</p>
                <p className="mt-0.5 text-[11px] text-ink/45">
                  Your job-search workspace
                </p>
              </div>
            </div>
            <button
              type="button"
              aria-label="Filter preview"
              className="grid size-9 place-items-center rounded-xl border border-ink/10 bg-white text-ink/55"
            >
              <FunnelSimple size={17} />
            </button>
          </div>

          <div className="grid grid-cols-3 gap-2.5 p-4 sm:gap-3 sm:p-5">
            {[
              { label: "Saved roles", value: "12", Icon: Briefcase },
              { label: "Applications", value: "08", Icon: PaperPlaneTilt },
              { label: "Follow-ups", value: "03", Icon: TrendUp },
            ].map(({ label, value, Icon }) => (
              <div
                key={label}
                className="min-w-0 rounded-xl border border-ink/[0.06] bg-white p-3 sm:p-4"
              >
                <span className="grid size-7 place-items-center rounded-lg bg-violet/10 text-violet">
                  <Icon size={15} weight="bold" />
                </span>
                <p className="mt-3 font-display text-2xl font-extrabold tracking-tight sm:text-3xl">
                  {value}
                </p>
                <p className="mt-1 text-[10px] leading-4 text-ink/50 sm:text-xs">
                  {label}
                </p>
              </div>
            ))}
          </div>

          <div className="px-4 pb-2 sm:px-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-sm font-extrabold">Recent applications</h3>
                <p className="mt-1 text-[11px] text-ink/45">
                  Example workspace data
                </p>
              </div>
              <span className="rounded-full bg-violet/10 px-2.5 py-1 text-[10px] font-bold text-violet">
                Preview
              </span>
            </div>
          </div>

          <div className="space-y-2.5 p-4 pt-3 sm:p-5 sm:pt-3">
            {jobs.map((job) => (
              <div
                key={job.company}
                className="flex items-center gap-3 rounded-xl border border-ink/[0.06] bg-white p-3 transition-transform hover:translate-x-0.5 sm:p-3.5"
              >
                <span
                  className={`grid size-10 shrink-0 place-items-center rounded-xl text-sm font-extrabold ${job.color}`}
                >
                  {job.initials}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-bold sm:text-sm">
                    {job.role}
                  </p>
                  <p className="mt-1 truncate text-[11px] text-ink/50">
                    {job.company} · {job.type}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-1 text-[9px] font-bold sm:text-[10px] ${job.statusColor}`}
                >
                  {job.status}
                </span>
              </div>
            ))}
          </div>

          <div className="mx-4 mb-4 flex items-center gap-3 rounded-xl border border-violet/10 bg-violet/[0.055] p-3 sm:mx-5 sm:mb-5 sm:p-4">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-white text-violet shadow-sm">
              <Sparkle size={18} weight="fill" />
            </span>
            <div>
              <p className="text-xs font-bold">Your search, in one place</p>
              <p className="mt-1 text-[10px] leading-relaxed text-ink/55 sm:text-xs">
                Review opportunities and plan your next action.
              </p>
            </div>
            <ArrowRight size={16} className="ml-auto shrink-0 text-violet" />
          </div>
        </div>
      </div>

      <div className="absolute -left-3 top-[28%] hidden items-center gap-2.5 rounded-2xl border border-white bg-white p-3.5 shadow-xl shadow-ink/10 sm:flex lg:-left-10">
        <span className="grid size-9 place-items-center rounded-xl bg-emerald-50 text-emerald-700">
          <Check size={18} weight="bold" />
        </span>
        <div>
          <p className="text-xs font-bold">Stay organized</p>
          <p className="mt-1 text-[10px] text-ink/50">One clear workflow</p>
        </div>
      </div>

      <div className="absolute -right-2 bottom-[12%] hidden items-center gap-2.5 rounded-2xl border border-white bg-white p-3.5 shadow-xl shadow-ink/10 sm:flex lg:-right-7">
        <span className="grid size-9 place-items-center rounded-xl bg-violet/10 text-violet">
          <Sparkle size={18} weight="fill" />
        </span>
        <div>
          <p className="text-xs font-bold">AI-assisted</p>
          <p className="mt-1 text-[10px] text-ink/50">Application materials</p>
        </div>
      </div>
    </div>
  );
}

function Features() {
  return (
    <section id="features" className="scroll-mt-24 px-5 py-24 sm:px-8 lg:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="max-w-2xl">
          <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-violet">
            Less chaos, more clarity
          </p>
          <h2 className="mt-4 font-display text-4xl font-extrabold leading-tight tracking-[-0.04em] sm:text-5xl">
            Everything around your job search,{" "}
            <span className="text-ink/40">working together.</span>
          </h2>
          <p className="mt-5 max-w-xl leading-7 text-ink/60">
            A focused workspace for the practical work behind your next career
            move, with AI assistance where it helps.
          </p>
        </div>

        <div className="mt-14 grid gap-5 md:grid-cols-3">
          {features.map(({ Icon, number, title, description }) => (
            <article
              key={number}
              className="group rounded-2xl border border-ink/[0.08] bg-white p-7 transition-all duration-200 hover:-translate-y-1 hover:border-violet/25 hover:shadow-xl hover:shadow-violet/[0.06] sm:p-8"
            >
              <div className="flex items-center justify-between">
                <span className="grid size-12 place-items-center rounded-2xl bg-violet/10 text-violet transition-colors group-hover:bg-violet group-hover:text-white">
                  <Icon size={23} weight="duotone" />
                </span>
                <span className="font-display text-sm font-bold text-ink/25">
                  {number}
                </span>
              </div>
              <h3 className="mt-8 font-display text-xl font-bold tracking-tight">
                {title}
              </h3>
              <p className="mt-3 text-sm leading-7 text-ink/60">
                {description}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section
      id="how-it-works"
      className="scroll-mt-24 border-y border-ink/[0.06] bg-white px-5 py-24 sm:px-8 lg:py-32"
    >
      <div className="mx-auto grid max-w-6xl gap-14 lg:grid-cols-[0.8fr_1.2fr]">
        <div>
          <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-violet">
            A simpler process
          </p>
          <h2 className="mt-4 font-display text-4xl font-extrabold leading-tight tracking-[-0.04em] sm:text-5xl">
            A little more structure. A lot more clarity.
          </h2>
          <p className="mt-5 max-w-md leading-7 text-ink/60">
            Turn a scattered job hunt into a repeatable process that you can
            manage and improve.
          </p>
          <a
            href="/dashboard"
            className="mt-8 inline-flex items-center gap-2 text-sm font-extrabold text-violet hover:gap-3"
          >
            Explore the workspace <ArrowRight size={17} />
          </a>
        </div>

        <ol className="space-y-0">
          {steps.map((step, index) => (
            <li
              key={step.number}
              className="relative flex gap-5 border-b border-ink/[0.08] py-7 first:pt-0 last:border-0 last:pb-0 sm:gap-7"
            >
              <div className="relative">
                <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-violet/10 font-display text-sm font-extrabold text-violet">
                  {step.number}
                </span>
                {index !== steps.length - 1 && (
                  <span className="absolute bottom-[-29px] left-1/2 h-7 w-px -translate-x-1/2 bg-violet/20" />
                )}
              </div>
              <div className="pb-1">
                <h3 className="font-display text-xl font-bold">{step.title}</h3>
                <p className="mt-2 max-w-lg text-sm leading-7 text-ink/60">
                  {step.description}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Pricing({
  yearly,
  setYearly,
}: {
  yearly: boolean;
  setYearly: (value: boolean) => void;
}) {
  return (
    <section id="pricing" className="scroll-mt-24 px-5 py-24 sm:px-8 lg:py-32">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div>
            <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-violet">
              Straightforward plans
            </p>
            <h2 className="mt-4 max-w-2xl font-display text-4xl font-extrabold tracking-[-0.04em] sm:text-5xl">
              Choose what fits your search.
            </h2>
            <p className="mt-4 text-sm leading-7 text-ink/60 sm:text-base">
              Start with the essentials and decide what you need as you go.
            </p>
          </div>

          <div
            role="group"
            aria-label="Billing period"
            className="inline-flex self-start rounded-xl border border-ink/[0.07] bg-white p-1 md:self-auto"
          >
            {[
              { label: "Monthly", value: false },
              { label: "Yearly", value: true },
            ].map(({ label, value }) => (
              <button
                key={label}
                type="button"
                aria-pressed={yearly === value}
                onClick={() => setYearly(value)}
                className={`rounded-lg px-4 py-2.5 text-sm font-bold transition-colors ${
                  yearly === value
                    ? "bg-violet text-white shadow-sm"
                    : "text-ink/55 hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-12 grid items-stretch gap-5 md:grid-cols-3">
          {plans.map((plan) => {
            const price =
              plan.monthly === null
                ? "Let's talk"
                : `$${yearly ? plan.yearly : plan.monthly}`;

            return (
              <article
                key={plan.name}
                className={`relative flex flex-col rounded-2xl border p-7 sm:p-8 ${
                  plan.featured
                    ? "border-violet bg-ink text-white shadow-2xl shadow-violet/15 md:-my-3 md:py-11"
                    : "border-ink/[0.08] bg-white"
                }`}
              >
                {plan.featured && (
                  <span className="absolute right-5 top-5 rounded-full bg-violet px-3 py-1 text-[10px] font-extrabold uppercase tracking-wide text-white">
                    Popular
                  </span>
                )}

                <h3 className="font-display text-xl font-extrabold">
                  {plan.name}
                </h3>
                <p
                  className={`mt-2 min-h-10 text-sm leading-6 ${
                    plan.featured ? "text-white/60" : "text-ink/55"
                  }`}
                >
                  {plan.description}
                </p>

                <div className="mt-7 flex min-h-[62px] items-end gap-2">
                  <span className="font-display text-4xl font-extrabold tracking-tight">
                    {price}
                  </span>
                  {plan.monthly !== null && (
                    <span
                      className={`mb-1 text-xs ${
                        plan.featured ? "text-white/55" : "text-ink/50"
                      }`}
                    >
                      / month
                    </span>
                  )}
                </div>

                <div
                  className={`my-7 border-t ${
                    plan.featured ? "border-white/10" : "border-ink/[0.08]"
                  }`}
                />

                <ul className="mb-8 flex-1 space-y-4">
                  {plan.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-start gap-3 text-sm leading-6"
                    >
                      <Check
                        size={17}
                        weight="bold"
                        className={`mt-0.5 shrink-0 ${
                          plan.featured ? "text-violet-300" : "text-violet"
                        }`}
                      />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>

                <a
                  href={plan.name === "Teams" ? "#contact" : "/dashboard"}
                  className={`inline-flex min-h-12 items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-bold transition-all ${
                    plan.featured
                      ? "bg-violet text-white hover:bg-violet/90"
                      : "border border-ink/10 hover:border-violet/30 hover:bg-violet/[0.04]"
                  }`}
                >
                  {plan.name === "Teams" ? "Discuss team needs" : "Get started"}
                  <ArrowRight size={15} weight="bold" />
                </a>
              </article>
            );
          })}
        </div>
        <p className="mt-5 text-xs leading-6 text-ink/45">
          Pricing and plan features are illustrative until billing and
          entitlements are configured in the application.
        </p>
      </div>
    </section>
  );
}

function FinalCTA() {
  return (
    <section id="contact" className="px-5 pb-20 sm:px-8 lg:pb-28">
      <div className="relative mx-auto max-w-6xl overflow-hidden rounded-[28px] bg-ink px-7 py-12 text-white sm:px-12 sm:py-16 lg:px-16">
        <div className="pointer-events-none absolute -right-20 -top-36 size-96 rounded-full bg-violet/40 blur-[100px]" />
        <div className="pointer-events-none absolute -bottom-32 left-1/3 size-72 rounded-full bg-fuchsia-500/20 blur-[100px]" />

        <div className="relative flex flex-col items-start justify-between gap-8 md:flex-row md:items-center">
          <div className="max-w-xl">
            <span className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-violet-200">
              <Sparkle size={15} weight="fill" /> Your next chapter
            </span>
            <h2 className="mt-4 font-display text-3xl font-extrabold leading-tight tracking-[-0.035em] sm:text-4xl lg:text-5xl">
              Make your job search feel manageable again.
            </h2>
            <p className="mt-4 max-w-lg text-sm leading-7 text-white/60 sm:text-base">
              Bring your applications into one place and take the next step
              with a clearer plan.
            </p>
          </div>

          <a
            href="/dashboard"
            className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-white px-6 py-4 text-sm font-extrabold text-ink transition-transform hover:-translate-y-0.5"
          >
            Open your workspace <ArrowRight size={17} weight="bold" />
          </a>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-ink/[0.07] bg-white px-5 py-10 sm:px-8">
      <div className="mx-auto flex max-w-6xl flex-col justify-between gap-6 sm:flex-row sm:items-center">
        <div>
          <Logo />
          <p className="mt-3 max-w-sm text-xs leading-6 text-ink/50">
            Tools to bring more structure and clarity to your job search.
          </p>
        </div>

        <div className="flex flex-wrap gap-x-6 gap-y-3 text-xs font-semibold text-ink/55">
          <a href="#features" className="hover:text-violet">
            Features
          </a>
          <a href="#how-it-works" className="hover:text-violet">
            How it works
          </a>
          <a href="#pricing" className="hover:text-violet">
            Pricing
          </a>
          <a href="/dashboard" className="hover:text-violet">
            Dashboard
          </a>
        </div>

        <p className="text-xs text-ink/40">
          © 2026 AI Applier
        </p>
      </div>
    </footer>
  );
}
