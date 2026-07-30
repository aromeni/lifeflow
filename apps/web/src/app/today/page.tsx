"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { BriefSectionView } from "@/components/BriefSectionView";
import { RateLimitNotice } from "@/components/RateLimitNotice";
import { Button } from "@/components/ui/Button";
import { AppShell, PageHeader } from "@/components/ui/AppShell";
import { Notice } from "@/components/ui/Notice";
import { api, ApiError, RateLimitError } from "@/lib/api";
import type { Brief, Me } from "@/lib/types";

type LoadState = "loading" | "generating" | "ready" | "no-brief" | "unauthenticated" | "error";

const STATUS_MESSAGES: Record<string, string> = {
  partial:
    "Some information could be incomplete: a source was unavailable or evidence could not be resolved. Details below.",
  degraded:
    "Optional model assistance was unavailable. This brief was composed entirely from deterministic rules — every fact is still evidence-backed.",
  empty: "There is nothing to report yet. Import sources and generate again.",
};

function formatGeneratedAt(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: timezone,
  }).format(new Date(iso));
}

// A compact orientation strip — counts only, no charts. Included because a
// brief with several sections genuinely benefits from an at-a-glance total
// before scrolling (Stage 10 §8); each count still links to its own
// section heading so the strip is a shortcut, not a second source of truth.
function SummaryStrip({ brief }: { brief: Brief }) {
  const counted = brief.sections.filter((section) => section.items.length > 0);
  if (counted.length === 0) return null;
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Counts by section">
      {counted.map((section) => (
        <li key={section.key}>
          <a
            href={`#section-${section.key}`}
            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-sm text-text-secondary transition-colors hover:border-border-strong hover:text-foreground"
          >
            <span className="font-semibold text-foreground">{section.items.length}</span>
            {section.label}
          </a>
        </li>
      ))}
    </ul>
  );
}

export default function TodayPage() {
  const [state, setState] = useState<LoadState>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [generateRetryAfter, setGenerateRetryAfter] = useState<number | null>(null);
  const generationInFlight = useRef(false);

  const load = useCallback(async () => {
    try {
      const profile = await api<Me>("/me");
      setMe(profile);
      const latest = await api<Brief>("/briefs/latest");
      setBrief(latest);
      setState("ready");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setState("unauthenticated");
      } else if (error instanceof ApiError && error.status === 404) {
        setState("no-brief");
      } else {
        setState("error");
      }
    }
  }, []);

  // Legitimate fetch-on-mount: setState only runs after awaited responses,
  // not synchronously in the effect body.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const generate = useCallback(async () => {
    // State-driven disabling happens on the next render. This synchronous
    // guard also prevents same-frame double clicks from issuing a second POST.
    if (generationInFlight.current) return;
    generationInFlight.current = true;
    setGenerateRetryAfter(null);
    setState("generating");
    try {
      const fresh = await api<Brief>("/briefs/generate", { method: "POST" });
      setBrief(fresh);
      setState("ready");
    } catch (error) {
      if (error instanceof RateLimitError) {
        // Not a provider failure and not "uncertain" — the request never
        // reached generation. Keep whatever was already on screen.
        setGenerateRetryAfter(error.retryAfterSeconds);
        setState((previous) =>
          previous === "generating" ? (brief ? "ready" : "no-brief") : previous,
        );
      } else if (error instanceof ApiError && error.status === 401) {
        setState("unauthenticated");
      } else {
        setState("error");
      }
    } finally {
      generationInFlight.current = false;
    }
  }, [brief]);

  if (state === "unauthenticated") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16">
        <p>
          You are not signed in.{" "}
          <Link href="/" className="underline">
            Start the demo
          </Link>{" "}
          first.
        </p>
      </main>
    );
  }

  const timezone = me?.timezone ?? "Europe/London";
  const statusMessage = brief ? STATUS_MESSAGES[brief.status] : undefined;

  // Computed once, then rendered into a single element that stays mounted
  // across every state transition — screen readers that require a live
  // region to already exist before its content changes must not lose this
  // announcement to a state-driven remount (see TryDemoButton for the same
  // pattern).
  let briefStatusText = "";
  if (state === "ready" && brief) {
    briefStatusText = `Generated ${formatGeneratedAt(brief.generated_at, timezone)} · version ${brief.version} · ${brief.status} · ${brief.generation_trigger === "scheduled" ? "scheduled" : "manual"}`;
  } else if (state === "loading") {
    briefStatusText = "Loading your brief…";
  } else if (state === "generating") {
    briefStatusText = "Generating a fresh brief from your sources…";
  } else if (state === "no-brief") {
    briefStatusText = "No brief yet.";
  } else if (state === "error") {
    briefStatusText = "Could not load your brief. Is the API running?";
  }

  return (
    <AppShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
        <PageHeader
          title="Today"
          description={
            <span data-testid="brief-status" aria-live="polite">
              {briefStatusText}
            </span>
          }
          actions={
            <Button
              data-testid="generate-brief"
              type="button"
              variant="primary"
              onClick={generate}
              disabled={state === "generating"}
            >
              {state === "generating" ? "Generating…" : "Generate brief"}
            </Button>
          }
        />

        {generateRetryAfter !== null && <RateLimitNotice retryAfterSeconds={generateRetryAfter} />}

        {state === "no-brief" && (
          <section className="flex flex-col gap-3">
            <p className="text-text-secondary">
              Generate your first daily brief. It is composed from your imported information, every
              item carries its source evidence, and nothing is actioned without your approval.
            </p>
          </section>
        )}

        {state === "ready" && brief && (
          <>
            <section aria-labelledby="summary-heading" className="flex flex-col gap-3">
              <h2 id="summary-heading" className="sr-only">
                Summary
              </h2>
              <p className="text-lg text-foreground">{brief.summary}</p>
              <SummaryStrip brief={brief} />
              {statusMessage ? (
                <Notice tone="info" role="status">
                  {statusMessage}
                </Notice>
              ) : null}
              {brief.notices.map((notice) => (
                <Notice key={notice.code} tone="info" role="status">
                  {notice.message}
                </Notice>
              ))}
            </section>

            <div className="flex flex-col gap-8">
              {brief.sections.map((section) => (
                <BriefSectionView key={section.key} section={section} timezone={timezone} />
              ))}
            </div>

            <footer className="flex flex-col gap-1 border-t border-border pt-4 text-sm text-text-tertiary">
              <span>
                Source window: {brief.source_window} · composed deterministically
                {brief.generation_metadata &&
                (brief.generation_metadata as Record<string, unknown>).llm_summary_used === true
                  ? " · summary sentences selected by the model from evidence-backed text"
                  : ""}
              </span>
              <Link href="/debug/source-items" className="underline">
                Developer view: raw normalised items
              </Link>
            </footer>
          </>
        )}
      </div>
    </AppShell>
  );
}
