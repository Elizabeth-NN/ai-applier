"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Show,
  SignInButton,
  SignUpButton,
  SignOutButton,
  UserButton,
} from "@clerk/nextjs";
import {
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
    <Link href="/" className="flex items-center gap-2.5">
      <span className="grid size-9 place-items-center rounded-xl bg-violet text-white">
        <RocketLaunch size={19} weight="fill" />
      </span>
      <span className="font-display text-lg font-extrabold tracking-tight text-ink">
        AI<span className="text-violet">Applier</span>
      </span>
    </Link>
  );
}

const linkClass =
  "text-sm font-semibold text-ink/65 transition-colors hover:text-violet";

const buttonClass =
  "inline-flex items-center justify-center rounded-xl px-4 py-2.5 text-sm font-bold transition";

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  function closeMenu() {
    setMenuOpen(false);
  }

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-ink/[0.08] bg-paper/95 backdrop-blur-xl">
      <nav
        aria-label="Main navigation"
        className="mx-auto flex h-[68px] max-w-7xl items-center justify-between px-5 sm:px-8"
      >
        <Logo />

        <div className="hidden items-center gap-7 md:flex">
          {links.map((link) => (
            <Link key={link.label} href={link.href} className={linkClass}>
              {link.label}
            </Link>
          ))}
        </div>

        <div className="hidden items-center gap-3 md:flex">
          <Show when="signed-out">
            <SignInButton mode="redirect">
              <button
                type="button"
                className={`${buttonClass} text-ink hover:bg-violet/5`}
              >
                Log in
              </button>
            </SignInButton>

            <SignUpButton mode="redirect">
              <button
                type="button"
                className={`${buttonClass} bg-violet text-white hover:bg-violet/90`}
              >
                Sign up
              </button>
            </SignUpButton>
          </Show>

          <Show when="signed-in">

            <UserButton />
            <SignOutButton redirectUrl="/">
              <button
                type="button"
                className={`${buttonClass} text-ink/70 hover:bg-violet/5 hover:text-violet`}
              >
                Log out
              </button>
            </SignOutButton>
          </Show>
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
              <Link
                key={link.label}
                href={link.href}
                onClick={closeMenu}
                className="rounded-xl px-4 py-3 text-sm font-semibold text-ink/70 hover:bg-violet/5 hover:text-violet"
              >
                {link.label}
              </Link>
            ))}

            <Show when="signed-out">
              <div className="mt-2 grid grid-cols-2 gap-3">
                <SignInButton mode="redirect">
                  <button
                    type="button"
                    onClick={closeMenu}
                    className={`${buttonClass} border border-ink/10 text-ink`}
                  >
                    Log in
                  </button>
                </SignInButton>

                <SignUpButton mode="redirect">
                  <button
                    type="button"
                    onClick={closeMenu}
                    className={`${buttonClass} bg-violet text-white`}
                  >
                    Sign up
                  </button>
                </SignUpButton>
              </div>
            </Show>

            <Show when="signed-in">

              <div className="mt-3 flex items-center justify-between rounded-xl border border-ink/10 bg-white p-3">
                <span className="text-sm font-semibold text-ink">
                  Your account
                </span>
                <UserButton />
              </div>

              <SignOutButton redirectUrl="/">
                <button
                  type="button"
                  onClick={closeMenu}
                  className="mt-2 rounded-xl px-4 py-3 text-left text-sm font-semibold text-ink/70 hover:bg-violet/5 hover:text-violet"
                >
                  Log out
                </button>
              </SignOutButton>
            </Show>
          </div>
        </div>
      )}
    </header>
  );
}
