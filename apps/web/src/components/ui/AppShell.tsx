"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

// The one persistent navigation shell for every authenticated screen
// (Stage 10 §5). Deliberately a slim top bar, not a permanent sidebar —
// a sidebar would cost real content width on the Today page's already-long
// list, and this app has exactly four top-level destinations. Wraps in
// each page rather than the Next.js root layout so the landing and
// onboarding screens (which have their own focused flow) never show it.
const LINKS = [
  { href: "/today", label: "Today", testId: "nav-today" },
  { href: "/approvals", label: "Approvals", testId: "approval-inbox-link" },
  { href: "/connections", label: "Connections", testId: "connections-link" },
  { href: "/audit-history", label: "Audit history", testId: "nav-audit-history" },
] as const;

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        className="sr-only focus-visible:not-sr-only focus-visible:absolute focus-visible:top-2 focus-visible:left-2 focus-visible:z-50 focus-visible:rounded-md focus-visible:bg-accent focus-visible:px-3 focus-visible:py-2 focus-visible:text-sm focus-visible:font-medium focus-visible:text-white"
      >
        Skip to main content
      </a>
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
          <Link
            href="/today"
            className="rounded-sm text-base font-semibold tracking-tight text-foreground"
          >
            LifeFlow AI
          </Link>
          <nav aria-label="Primary" className="order-3 w-full sm:order-0 sm:w-auto">
            <ul className="flex flex-wrap gap-x-1 gap-y-1 text-sm">
              {LINKS.map((link) => {
                const current = pathname === link.href;
                return (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      data-testid={link.testId}
                      aria-current={current ? "page" : undefined}
                      className={`inline-block rounded-md px-3 py-1.5 font-medium transition-colors ${
                        current
                          ? "bg-accent-subtle text-accent-subtle-text"
                          : "text-text-secondary hover:bg-surface-raised hover:text-foreground"
                      }`}
                    >
                      {link.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
          <Link
            href="/settings"
            data-testid="nav-settings"
            aria-current={pathname === "/settings" ? "page" : undefined}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              pathname === "/settings"
                ? "bg-accent-subtle text-accent-subtle-text"
                : "text-text-secondary hover:bg-surface-raised hover:text-foreground"
            }`}
          >
            Settings
          </Link>
        </div>
      </header>
      <main id="main-content" className="flex-1 bg-background">
        {children}
      </main>
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 border-b border-border pb-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
          {title}
        </h1>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {description ? <p className="max-w-2xl text-sm text-text-secondary">{description}</p> : null}
    </div>
  );
}
