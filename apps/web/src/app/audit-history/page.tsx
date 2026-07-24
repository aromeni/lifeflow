"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type {
  AuditHistoryCategory,
  AuditHistoryItem,
  AuditHistoryPeriod,
  AuditHistoryResponse,
  Me,
} from "@/lib/types";

type LoadState = "loading" | "ready" | "unauthenticated" | "error";

const CATEGORY_OPTIONS: Array<{ value: AuditHistoryCategory; label: string }> = [
  { value: "all", label: "All activity" },
  { value: "actions", label: "Actions" },
  { value: "briefs", label: "Briefs" },
  { value: "connections", label: "Connections" },
  { value: "privacy", label: "Privacy" },
  { value: "preferences", label: "Preferences" },
  { value: "account", label: "Account" },
];

const PERIOD_OPTIONS: Array<{ value: AuditHistoryPeriod; label: string }> = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "all", label: "All time" },
];

const CATEGORY_LABELS: Record<AuditHistoryCategory, string> = Object.fromEntries(
  CATEGORY_OPTIONS.map(({ value, label }) => [value, label]),
) as Record<AuditHistoryCategory, string>;

const TONE_LABELS: Record<AuditHistoryItem["tone"], string> = {
  neutral: "Recorded",
  success: "Completed",
  warning: "Attention",
  failure: "Not completed",
};

function historyPath(
  category: AuditHistoryCategory,
  period: AuditHistoryPeriod,
  cursor?: string,
): string {
  const query = new URLSearchParams({ category, period });
  if (cursor) query.set("cursor", cursor);
  return `/audit-history?${query.toString()}`;
}

function formatTimestamp(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(iso));
}

export default function AuditHistoryPage() {
  const [state, setState] = useState<LoadState>("loading");
  const [items, setItems] = useState<AuditHistoryItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [timezone, setTimezone] = useState("UTC");
  const [category, setCategory] = useState<AuditHistoryCategory>("all");
  const [period, setPeriod] = useState<AuditHistoryPeriod>("7d");
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState("");

  const loadFirstPage = useCallback(async () => {
    try {
      const [history, me] = await Promise.all([
        api<AuditHistoryResponse>(historyPath(category, period)),
        api<Me>("/me"),
      ]);
      setItems(history.items);
      setNextCursor(history.next_cursor);
      setTimezone(me.timezone);
      setLoadMoreError("");
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiError && error.status === 401 ? "unauthenticated" : "error");
    }
  }, [category, period]);

  useEffect(() => {
    // Filter changes intentionally replace the page and its cursor.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState("loading");
    void loadFirstPage();
  }, [loadFirstPage]);

  async function loadMore() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    setLoadMoreError("");
    try {
      const history = await api<AuditHistoryResponse>(historyPath(category, period, nextCursor));
      setItems((current) => [...current, ...history.items]);
      setNextCursor(history.next_cursor);
    } catch (error) {
      setLoadMoreError(
        error instanceof ApiError ? error.message : "More audit history could not be loaded.",
      );
    } finally {
      setLoadingMore(false);
    }
  }

  if (state === "unauthenticated") {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16">
        <p>
          You are not signed in. <Link href="/">Start the demo</Link> first.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap gap-4 text-sm">
          <Link href="/today" className="underline">
            ← Back to Today
          </Link>
          <Link href="/connections" className="underline">
            Privacy &amp; Connections
          </Link>
        </div>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Audit history</h1>
          <p className="mt-2 max-w-2xl">
            A plain-language record of important LifeFlow activity. Private content, provider
            identifiers, technical metadata, and error details are never shown here.
          </p>
        </div>
      </header>

      <section aria-labelledby="audit-history-filters" className="flex flex-col gap-3">
        <h2 id="audit-history-filters" className="font-semibold">
          Filter history
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            Activity
            <select
              value={category}
              onChange={(event) => setCategory(event.target.value as AuditHistoryCategory)}
              className="rounded border border-current/30 bg-background px-3 py-2"
            >
              {CATEGORY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Time period
            <select
              value={period}
              onChange={(event) => setPeriod(event.target.value as AuditHistoryPeriod)}
              className="rounded border border-current/30 bg-background px-3 py-2"
            >
              {PERIOD_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <p aria-live="polite" className="text-sm opacity-70">
        {state === "loading" && "Loading your audit history…"}
        {state === "error" && "Could not load your audit history. Is the API running?"}
      </p>

      {state === "error" ? (
        <button
          type="button"
          onClick={() => {
            setState("loading");
            void loadFirstPage();
          }}
          className="w-fit rounded border border-current/30 px-4 py-2 text-sm"
        >
          Try again
        </button>
      ) : null}

      {state === "ready" ? (
        <section aria-labelledby="audit-history-results" data-testid="audit-history">
          <h2 id="audit-history-results" className="sr-only">
            Audit history results
          </h2>
          {items.length === 0 ? (
            <p className="rounded border border-current/20 p-5 text-sm">
              No {CATEGORY_LABELS[category].toLowerCase()} was recorded in this time period.
            </p>
          ) : (
            <ol className="flex flex-col gap-3">
              {items.map((item) => (
                <li
                  key={item.id}
                  className="grid gap-2 rounded-lg border border-current/20 p-5 sm:grid-cols-[1fr_auto]"
                >
                  <div>
                    <h3 className="font-semibold">{item.title}</h3>
                    <p className="mt-1 text-sm opacity-80">{item.summary}</p>
                    <p className="mt-2 text-xs opacity-65">
                      {item.actor === "you" ? "You" : "LifeFlow"} · {CATEGORY_LABELS[item.category]}{" "}
                      · {TONE_LABELS[item.tone]}
                    </p>
                  </div>
                  <time dateTime={item.occurred_at} className="text-xs opacity-65 sm:text-right">
                    {formatTimestamp(item.occurred_at, timezone)}
                  </time>
                </li>
              ))}
            </ol>
          )}
          {loadMoreError ? (
            <p role="alert" className="mt-4 text-sm text-red-700 dark:text-red-400">
              {loadMoreError}
            </p>
          ) : null}
          {nextCursor ? (
            <button
              type="button"
              onClick={loadMore}
              disabled={loadingMore}
              className="mt-5 rounded border border-current/30 px-4 py-2 text-sm disabled:opacity-50"
            >
              {loadingMore ? "Loading…" : "Load more"}
            </button>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
