"use client";
import { useEffect, useState } from "react";
import {
  RocketLaunch, ArrowRight, Check, MagnifyingGlass, FileText, PaperPlaneTilt,
  CalendarCheck, XLogo, LinkedinLogo, InstagramLogo, YoutubeLogo,
} from "@phosphor-icons/react";

const navLinks = [["Features", "#how"], ["How it works", "#how"], ["Pricing", "#pricing"], ["Enterprise", "#pricing"]];

const feed = [
  { Icon: MagnifyingGlass, text: "Found 14 new roles matching your profile", meta: "Scanned 52 job boards" },
  { Icon: FileText, text: "Tailored your resume for Senior Product Designer", meta: "Highlighted 6 matching skills" },
  { Icon: PaperPlaneTilt, text: "Sent application to Northwind Labs", meta: "98% match" },
  { Icon: CalendarCheck, text: "Interview request from Fieldnote", meta: "Pick a time by Friday" },
  { Icon: MagnifyingGlass, text: "Found 9 new remote roles", meta: "Scanned 52 job boards" },
  { Icon: PaperPlaneTilt, text: "Sent application to Lumen Health", meta: "94% match" },
];

const steps = [
  ["Tell it what you want", "Upload your resume and set your target roles, salary range and locations."],
  ["Your agent does the legwork", "It scans boards daily, tailors your resume and cover letter, and applies to roles that fit."],
  ["You show up to interviews", "Replies land in one inbox. You approve, reschedule or pass."],
];

type Plan = {
  name: string;
  tagline: string;
  monthly?: number;
  yearly?: number;
  custom?: boolean;
  features: string[];
  cta: string;
  featured?: boolean;
};

const plans: Plan[] = [
  {
    name: "Starter",
    tagline: "Try it with a few applications",
    monthly: 0,
    features: [
      "Job application tracking",
      "Basic job matching",
      "One resume profile",
    ],
    cta: "Start free",
  },
  {
    name: "Pro",
    tagline: "For an active job search",
    monthly: 19,
    yearly: 15,
    features: [
      "Advanced job-search organization",
      "Resume and cover letter assistance",
      "Application tracking",
      "Interview preparation",
    ],
    cta: "Upgrade to Pro",
    featured: true,
  },
  {
    name: "Enterprise",
    tagline: "For teams and universities",
    custom: true,
    features: [
      "Team management",
      "Centralized application tracking",
      "Custom integrations",
    ],
    cta: "Contact sales",
  },
];
const footerColumns = [
  ["Product", ["Features", "How it works", "Pricing", "Enterprise"]],
  ["Company", ["About", "Careers", "Blog", "Press"]],
  ["Resources", ["Help center", "Resume templates", "Privacy policy", "Terms of service"]],
] as const;

const Logo = () => (
  <a href="#" className="flex items-center gap-2.5 font-display text-xl font-bold tracking-tight text-ink">
    <span className="grid h-9 w-9 place-items-center rounded-lg bg-violet text-white"><RocketLaunch weight="fill" className="h-5 w-5" /></span>
    AIApplier
  </a>
);

export default function AIApplierLanding() {
  return (
    <div className="min-h-screen bg-paper text-ink">
      <Nav /><Hero /><Proof /><HowItWorks /><Pricing /><Footer />
    </div>
  );
}

function Nav() {
  return (
    <nav className="fixed inset-x-0 top-0 z-50 h-16 border-b border-ink/10 bg-paper/80 backdrop-blur-md">
      <div className="mx-auto flex h-full max-w-6xl items-center justify-between px-6">
        <Logo />
        <div className="hidden items-center gap-8 md:flex">
          {navLinks.map(([l, h]) => <a key={l} href={h} className="text-sm font-semibold text-ink/70 hover:text-violet">{l}</a>)}
        </div>
        <div className="flex items-center gap-2">
          <button className="hidden px-4 py-2 text-sm font-semibold text-ink/70 hover:text-violet sm:block">Log in</button>
          <button className="btn rounded-lg bg-violet px-4 py-2 text-sm font-semibold text-white">Start free</button>
        </div>
      </div>
    </nav>
  );
}

function Hero() {
  return (
    <section className="px-6 pb-20 pt-32 md:pt-40">
      <div className="mx-auto grid max-w-6xl items-center gap-14 lg:grid-cols-[1.1fr_1fr]">
        <div>
          <h1 className="font-display text-5xl font-extrabold leading-[1.02] tracking-tight sm:text-6xl lg:text-7xl">
            Apply to 200 jobs this week. Interview for the 10 that fit.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-relaxed text-ink/65">
            AIApplier finds roles, tailors your resume and cover letter for each one, and sends the application while you get on with your day.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <button className="btn flex items-center gap-2 rounded-xl bg-violet px-6 py-3.5 text-base font-semibold text-white">
              Hire your AI agent <ArrowRight weight="bold" className="h-4 w-4" />
            </button>
            <a href="#how" className="rounded-xl border border-ink/15 px-6 py-3.5 text-base font-semibold hover:bg-ink/5">See how it works</a>
          </div>
          <p className="mt-6 text-sm text-ink/55">Free plan, no card needed. Rated 4.8 by 12,000+ job seekers.</p>
        </div>
        <AgentFeed />
      </div>
    </section>
  );
}

function AgentFeed() {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setN((v) => v + 1), 3000);
    return () => clearInterval(t);
  }, []);
  const items = [3, 2, 1, 0].map((k) => ({ ...feed[(n + 3 - k + feed.length * 10) % feed.length], key: n - k }));
  return (
    <div className="rounded-2xl bg-ink p-5 text-white shadow-2xl shadow-violet/20 sm:p-6" aria-live="off">
      <div className="mb-5 flex items-center justify-between">
        <div className="flex items-center gap-2.5 text-sm font-semibold">
          <span className="relative flex h-2.5 w-2.5"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:hidden" /><span className="relative h-2.5 w-2.5 rounded-full bg-emerald-400" /></span>
          Your agent is working
        </div>
        <span className="text-xs text-white/50">Today</span>
      </div>
      <ul className="space-y-2.5">
        {items.map(({ Icon, text, meta, key }, i) => (
          <li key={key} className={`feed-in flex items-start gap-3 rounded-xl p-3.5 ${i === 3 ? "bg-white/12 ring-1 ring-violet/60" : "bg-white/[0.05] opacity-70"}`}>
            <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-violet/25 text-violet-200"><Icon weight="fill" className="h-4 w-4" /></span>
            <div><p className="text-sm font-semibold leading-snug">{text}</p><p className="mt-0.5 text-xs text-white/50">{meta}</p></div>
          </li>
        ))}
      </ul>
      <div className="mt-5 grid grid-cols-3 gap-3 border-t border-white/10 pt-5 text-center">
        {[["1,248", "Jobs matched"], ["186", "Applications sent"], ["11", "Interviews"]].map(([v, l]) => (
          <div key={l}><p className="font-display text-2xl font-bold">{v}</p><p className="text-xs text-white/50">{l}</p></div>
        ))}
      </div>
    </div>
  );
}

function Proof() {
  return (
    <section className="border-y border-ink/10 bg-white px-6 py-10">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-6 md:flex-row">
        <p className="max-w-xs text-center text-sm font-semibold text-ink/60 md:text-left">Job seekers using AIApplier have been hired at companies like</p>
        <div className="flex flex-wrap justify-center gap-x-10 gap-y-3 font-display text-xl font-bold text-ink/35">
          {["Google", "Spotify", "Microsoft", "Meta", "Amazon"].map((c) => <span key={c}>{c}</span>)}
        </div>
      </div>
    </section>
  );
}

function HowItWorks() {
  return (
    <section id="how" className="scroll-mt-16 px-6 py-24">
      <div className="mx-auto max-w-6xl">
        <h2 className="max-w-xl font-display text-4xl font-extrabold tracking-tight md:text-5xl">Set it up once. Your agent handles the rest.</h2>
        <ol className="mt-14 grid gap-10 md:grid-cols-3">
          {steps.map(([t, d], i) => (
            <li key={t} className="border-t-2 border-ink pt-5">
              <span className="font-display text-sm font-bold text-violet">Step {i + 1}</span>
              <h3 className="mt-2 font-display text-xl font-bold">{t}</h3>
              <p className="mt-2 leading-relaxed text-ink/65">{d}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Pricing() {
  const [yearly, setYearly] = useState(true);
  return (
    <section id="pricing" className="scroll-mt-16 bg-white px-6 py-24">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div>
            <h2 className="font-display text-4xl font-extrabold tracking-tight md:text-5xl">Start free. Upgrade when interviews start.</h2>
            <p className="mt-3 text-lg text-ink/65">Cancel anytime.</p>
          </div>
          <div role="group" aria-label="Billing period" className="inline-flex self-start rounded-lg bg-ink/5 p-1 text-sm font-semibold md:self-auto">
            {([["Monthly", false], ["Yearly (save 20%)", true]] as const).map(([l, v]) => (
              <button key={l} aria-pressed={yearly === v} onClick={() => setYearly(v)}
                className={`rounded-md px-4 py-2 transition-colors ${yearly === v ? "bg-white shadow-sm" : "text-ink/60"}`}>{l}</button>
            ))}
          </div>
        </div>

        <div className="mt-12 grid items-stretch gap-6 md:grid-cols-3">
          {plans.map((p) => {
            const price = p.custom ? "Custom" : `$${yearly && p.yearly != null ? p.yearly : p.monthly}`;
            return (
              <div key={p.name} className={`flex flex-col rounded-2xl p-8 ${p.featured ? "bg-ink text-white md:-my-4 md:py-12" : "border border-ink/12 bg-paper"}`}>
                <div className="flex items-center justify-between">
                  <h3 className="font-display text-xl font-bold">{p.name}</h3>
                  {p.featured && <span className="rounded-full bg-violet px-3 py-1 text-xs font-semibold">Most popular</span>}
                </div>
                <p className={`mt-1 text-sm ${p.featured ? "text-white/60" : "text-ink/60"}`}>{p.tagline}</p>
                <p className="mb-8 mt-6 flex items-end gap-1">
                  <span className="font-display text-5xl font-extrabold tracking-tight">{price}</span>
                  {!p.custom && <span className={`mb-1.5 text-sm ${p.featured ? "text-white/60" : "text-ink/60"}`}>/month</span>}
                </p>
                <ul className="mb-10 flex-1 space-y-3 text-sm">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-3"><Check weight="bold" className={`mt-0.5 h-4 w-4 shrink-0 ${p.featured ? "text-violet-300" : "text-violet"}`} />{f}</li>
                  ))}
                </ul>
                <button className={`btn rounded-xl py-3.5 text-sm font-semibold ${p.featured ? "bg-violet text-white" : "border border-ink/20 hover:bg-ink/5"}`}>{p.cta}</button>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="px-6 pb-10 pt-20">
      <div className="mx-auto max-w-6xl">
        <div className="mb-16 flex flex-col items-start justify-between gap-6 rounded-2xl bg-violet p-8 text-white md:flex-row md:items-center md:p-12">
          <h2 className="max-w-md font-display text-3xl font-extrabold leading-tight md:text-4xl">Your next role is already in someone’s inbox. Get there first.</h2>
          <button className="rounded-xl bg-white px-6 py-3.5 text-base font-semibold text-violet hover:bg-paper">Hire your AI agent</button>
        </div>
        <div className="grid gap-12 md:grid-cols-12">
          <div className="md:col-span-5">
            <Logo />
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-ink/60">Your AI agent for finding and applying to the right jobs.</p>
            <form className="mt-6 flex max-w-sm gap-2" onSubmit={(e) => e.preventDefault()}>
              <label htmlFor="email" className="sr-only">Email address</label>
              <input id="email" type="email" placeholder="Email address" className="min-w-0 flex-1 rounded-lg border border-ink/20 bg-white px-4 py-3 text-sm placeholder:text-ink/40" />
              <button className="btn rounded-lg bg-ink px-5 py-3 text-sm font-semibold text-white">Subscribe</button>
            </form>
          </div>
          {footerColumns.map(([title, links], i) => (
            <div key={title} className={i === 2 ? "md:col-span-3" : "md:col-span-2"}>
              <h3 className="mb-4 text-sm font-bold">{title}</h3>
              <ul className="space-y-3 text-sm text-ink/60">
                {links.map((l) => <li key={l}><a href="#" className="hover:text-violet">{l}</a></li>)}
              </ul>
            </div>
          ))}
        </div>
        <div className="mt-14 flex flex-col items-center justify-between gap-5 border-t border-ink/10 pt-8 sm:flex-row">
          <p className="text-xs text-ink/50">© 2026 AIApplier. All rights reserved.</p>
          <div className="flex gap-2">
            {([[XLogo, "X"], [LinkedinLogo, "LinkedIn"], [InstagramLogo, "Instagram"], [YoutubeLogo, "YouTube"]] as const).map(([Icon, name]) => (
              <a key={name} href="#" aria-label={name} className="grid h-9 w-9 place-items-center rounded-full border border-ink/15 text-ink/55 hover:text-violet"><Icon className="h-4 w-4" /></a>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
}