
"use client";

import { useState } from "react";
import {
  ArrowRight,
  List,
  X,
  RocketLaunch,
} from "@phosphor-icons/react";

const links = [
  { label: "Home", href: "/" },
  { label: "Features", href: "/#features" },
  { label: "How it works", href: "/#how-it-works" },
  { label: "Pricing", href: "/#pricing" },
  { label: "Dashboard", href: "/dashboard" },
];

function Logo() {
  return (
    <a href="/" className="flex items-center gap-2.5">
      <span className="grid size-9 place-items-center rounded-xl bg-violet text-white">
        <RocketLaunch size={19} weight="fill" />
      </span>
      <span className="font-display text-lg font-extrabold tracking-tight text-ink">
        AI<span className="text-violet">Applier</span>
      </span>
    </a>
  );
}

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-ink/[0.08] bg-paper/95 backdrop-blur-xl">
      <nav
        aria-label="Main navigation"
        className="mx-auto flex h-[68px] max-w-7xl items-center justify-between px-5 sm:px-8"
      >
        <Logo />

        <div className="hidden items-center gap-7 md:flex">
          {links.map((link) => (
            <a
              key={link.label}
              href={link.href}
              className="text-sm font-semibold text-ink/65 transition-colors hover:text-violet"
            >
              {link.label}
            </a>
          ))}
        </div>

        <div className="hidden md:block">
          <a
            href="/dashboard"
            className="inline-flex items-center gap-2 rounded-xl bg-violet px-4 py-2.5 text-sm font-bold text-white transition hover:bg-violet/90"
          >
            Open workspace <ArrowRight size={15} weight="bold" />
          </a>
        </div>

        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-label={menuOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={menuOpen}
          aria-controls="site-mobile-menu"
          className="grid size-10 place-items-center rounded-xl border border-ink/10 bg-white text-ink md:hidden"
        >
          {menuOpen ? <X size={21} /> : <List size={23} />}
        </button>
      </nav>

      {menuOpen && (
        <div
          id="site-mobile-menu"
          className="border-t border-ink/[0.08] bg-paper px-5 pb-5 pt-3 shadow-lg md:hidden"
        >
          <div className="mx-auto flex max-w-7xl flex-col gap-1">
            {links.map((link) => (
              <a
                key={link.label}
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className="rounded-xl px-4 py-3 text-sm font-semibold text-ink/70 hover:bg-violet/5 hover:text-violet"
              >
                {link.label}
              </a>
            ))}

            <a
              href="/dashboard"
              onClick={() => setMenuOpen(false)}
              className="mt-2 flex items-center justify-center gap-2 rounded-xl bg-violet px-4 py-3 text-sm font-bold text-white"
            >
              Open workspace <ArrowRight size={15} weight="bold" />
            </a>
          </div>
        </div>
      )}
    </header>
  );
}
