"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { BriefSectionView } from "@/components/BriefSectionView";
import { api, ApiError } from "@/lib/api";
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

export default function TodayPage() {
  const [state, setState] = useState<LoadState>("loading");
  const [me, setMe] = useState<Me | null>(null);
  const [brief, setBrief] = useState<Brief | null>(null);
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
    setState("generating");
    try {
      const fresh = await api<Brief>("/briefs/generate", { method: "POST" });
      setBrief(fresh);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiError && error.status === 401 ? "unauthenticated" : "error");
    } finally {
      generationInFlight.current = false;
    }
  }, []);

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

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="text-3xl font-semibold tracking-tight">Today</h1>
          <div className="flex items-center gap-3">
            <Link href="/approvals" data-testid="approval-inbox-link" className="text-sm underline">
              Review approvals
            </Link>
            <button
              data-testid="generate-brief"
              type="button"
              onClick={generate}
              disabled={state === "generating"}
              className="rounded border border-current/40 px-3 py-1 text-sm disabled:opacity-50"
            >
              {state === "generating" ? "Generating…" : "Generate brief"}
            </button>
          </div>
        </div>
        <p data-testid="brief-status" aria-live="polite" className="text-sm opacity-70">
          {state === "loading" && "Loading your brief…"}
          {state === "generating" && "Generating a fresh brief from your sources…"}
          {state === "ready" &&
            brief &&
            `Generated ${formatGeneratedAt(brief.generated_at, timezone)} · version ${brief.version} · ${brief.status}`}
          {state === "no-brief" && "No brief yet."}
          {state === "error" && "Could not load your brief. Is the API running?"}
        </p>
      </header>

      {state === "no-brief" && (
        <section className="flex flex-col gap-3">
          <p>
            Generate your first daily brief. It is composed from your imported information, every
            item carries its source evidence, and nothing is actioned without your approval.
          </p>
        </section>
      )}

      {state === "ready" && brief && (
        <>
          <section aria-labelledby="summary-heading" className="flex flex-col gap-2">
            <h2 id="summary-heading" className="sr-only">
              Summary
            </h2>
            <p className="text-lg">{brief.summary}</p>
            {statusMessage ? (
              <p role="status" className="rounded border border-current/30 px-3 py-2 text-sm">
                Note: {statusMessage}
              </p>
            ) : null}
            {brief.notices.map((notice) => (
              <p
                key={notice.code}
                role="status"
                className="rounded border border-current/30 px-3 py-2 text-sm"
              >
                {notice.message}
              </p>
            ))}
          </section>

          {brief.sections.map((section) => (
            <BriefSectionView key={section.key} section={section} timezone={timezone} />
          ))}

          <footer className="flex flex-col gap-1 text-sm opacity-70">
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
    </main>
  );
}
