"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell, PageHeader } from "@/components/ui/AppShell";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
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

const TONE_BADGE: Record<AuditHistoryItem["tone"], "neutral" | "success" | "warning" | "danger"> = {
  neutral: "neutral",
  success: "success",
  warning: "warning",
  failure: "danger",
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

function recordWord(n: number): string {
  return n === 1 ? "record" : "records";
}

// Zero-value counts are omitted — "0 records deleted" is noise, not clarity —
// and preserved is always phrased distinctly from deleted so the two are
// never conflated.
function countLines(item: AuditHistoryItem): string[] {
  const lines: string[] = [];
  if (item.deleted_count) {
    lines.push(`${item.deleted_count} ${recordWord(item.deleted_count)} deleted`);
  }
  if (item.preserved_count) {
    lines.push(
      `${item.preserved_count} ${recordWord(item.preserved_count)} preserved for reconciliation`,
    );
  }
  if (item.failed_count) {
    lines.push(`${item.failed_count} ${recordWord(item.failed_count)} could not be processed`);
  }
  return lines;
}

const selectStyle =
  "rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-foreground";

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
    <AppShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
        <PageHeader
          title="Audit history"
          description="A plain-language record of important LifeFlow activity. Private content, provider identifiers, technical metadata, and error details are never shown here."
        />

        <section
          aria-labelledby="audit-history-filters"
          className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5 shadow-xs"
        >
          <h2 id="audit-history-filters" className="text-sm font-semibold text-foreground">
            Filter history
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm text-foreground">
              Activity
              <select
                value={category}
                onChange={(event) => setCategory(event.target.value as AuditHistoryCategory)}
                className={selectStyle}
              >
                {CATEGORY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-foreground">
              Time period
              <select
                value={period}
                onChange={(event) => setPeriod(event.target.value as AuditHistoryPeriod)}
                className={selectStyle}
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

        <p aria-live="polite" className="text-sm text-text-secondary">
          {state === "loading" && "Loading your audit history…"}
          {state === "error" && "Could not load your audit history. Is the API running?"}
        </p>

        {state === "error" ? (
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setState("loading");
              void loadFirstPage();
            }}
          >
            Try again
          </Button>
        ) : null}

        {state === "ready" ? (
          <section aria-labelledby="audit-history-results" data-testid="audit-history">
            <h2 id="audit-history-results" className="sr-only">
              Audit history results
            </h2>
            {items.length === 0 ? (
              <p className="rounded-lg border border-border bg-surface p-5 text-sm text-text-secondary">
                No {CATEGORY_LABELS[category].toLowerCase()} was recorded in this time period.
              </p>
            ) : (
              <ol className="flex flex-col gap-3">
                {items.map((item) => (
                  <li
                    key={item.id}
                    className="grid gap-2 rounded-lg border border-border bg-surface p-5 shadow-xs sm:grid-cols-[1fr_auto]"
                  >
                    <div>
                      <h3 className="flex flex-wrap items-center gap-2 font-semibold text-foreground">
                        {item.title}
                        {item.action_type ? (
                          <Badge tone="neutral" uppercase={false} testId="audit-action-type">
                            {item.action_type}
                          </Badge>
                        ) : null}
                      </h3>
                      <p className="mt-1 text-sm text-text-secondary">{item.summary}</p>
                      {item.reason ? (
                        <p data-testid="audit-reason" className="mt-1 text-xs text-text-tertiary">
                          Reason: {item.reason}
                        </p>
                      ) : null}
                      {countLines(item).length > 0 ? (
                        <ul data-testid="audit-counts" className="mt-1 text-xs text-text-tertiary">
                          {countLines(item).map((line) => (
                            <li key={line}>{line}</li>
                          ))}
                        </ul>
                      ) : null}
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-text-tertiary">
                        <span>{item.actor === "you" ? "You" : "LifeFlow"}</span>
                        <span aria-hidden="true">·</span>
                        <span>{CATEGORY_LABELS[item.category]}</span>
                        <Badge tone={TONE_BADGE[item.tone]} uppercase={false}>
                          {TONE_LABELS[item.tone]}
                        </Badge>
                      </div>
                    </div>
                    <time
                      dateTime={item.occurred_at}
                      className="text-xs text-text-tertiary sm:text-right"
                    >
                      {formatTimestamp(item.occurred_at, timezone)}
                    </time>
                  </li>
                ))}
              </ol>
            )}
            {loadMoreError ? (
              <div className="mt-4">
                <Notice tone="danger" role="alert">
                  {loadMoreError}
                </Notice>
              </div>
            ) : null}
            {nextCursor ? (
              <Button
                type="button"
                variant="secondary"
                className="mt-5"
                onClick={loadMore}
                disabled={loadingMore}
              >
                {loadingMore ? "Loading…" : "Load more"}
              </Button>
            ) : null}
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
