"use client";

// Stage 9 Privacy & Connections Control Centre. GET /privacy/summary remains
// the privacy-safe read projection; existing connection controls, Phase 2
// deletion controls, and the Phase 3 audit-history link stay distinct.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { rateLimitMessage } from "@/components/RateLimitNotice";
import { API_URL, api, ApiError, RateLimitError } from "@/lib/api";
import type { GoogleSyncResult, PrivacySummary } from "@/lib/types";

import DeletionControls from "./DeletionControls";

type LoadState = "loading" | "ready" | "unauthenticated" | "error";

// Stage 9 Delivery Phase 5 (§16): a Google sync failure is not one thing —
// distinguish "temporarily unavailable, safe to try again shortly" from
// "won't succeed by retrying" using the API's closed retryable/dependency
// fields, rather than a single undifferentiated error string.
type SyncErrorState = { message: string; retryable: boolean | null };

function syncErrorState(error: unknown): SyncErrorState {
  if (error instanceof RateLimitError) {
    // Never shown as a sync failure or provider outcome — the request
    // never reached Google. Evidence-freshness state is untouched.
    return { message: rateLimitMessage(error.retryAfterSeconds), retryable: null };
  }
  if (error instanceof ApiError && error.dependency === "google") {
    return { message: error.message, retryable: error.retryable ?? null };
  }
  return {
    message: error instanceof ApiError ? error.message : "Google sync could not complete.",
    retryable: null,
  };
}

const FRESHNESS_COPY: Record<string, string> = {
  fresh: "Fresh — synced within the last 24 hours",
  aging: "Aging — synced within the last week",
  stale: "Stale — last synced over a week ago",
};

const INVENTORY_LABELS: Array<{ key: keyof PrivacySummary["inventory"]; label: string }> = [
  { key: "connected_accounts", label: "Connected accounts" },
  { key: "source_items", label: "Imported emails & events" },
  { key: "signals", label: "Detected signals" },
  { key: "briefs", label: "Daily briefs" },
  { key: "brief_versions", label: "Brief versions (all regenerations)" },
  { key: "action_proposals", label: "Action proposals" },
  { key: "action_executions", label: "Executions" },
  { key: "scheduled_brief_runs", label: "Scheduled brief runs" },
  { key: "preferences", label: "Explicit preferences" },
  { key: "memory_items", label: "Learned-preference items" },
  { key: "memory_evidence", label: "Learned-preference evidence" },
  { key: "audit_events", label: "Audit records" },
];

export default function ConnectionsPage() {
  const [state, setState] = useState<LoadState>("loading");
  const [summary, setSummary] = useState<PrivacySummary | null>(null);
  const [pending, setPending] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<GoogleSyncResult | null>(null);
  const [syncError, setSyncError] = useState<SyncErrorState | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await api<PrivacySummary>("/privacy/summary");
      setSummary(response);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiError && error.status === 401 ? "unauthenticated" : "error");
    }
  }, []);

  useEffect(() => {
    // The only fetch happens here, once, in response to the component
    // mounting — never on a timer and never as a side effect of a provider
    // sync, so opening or refreshing this page never causes Google traffic.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const google = summary?.connections.find((account) => account.provider === "google");

  async function disconnectGoogle() {
    if (pending) return;
    setPending(true);
    try {
      await api("/connected-accounts/google/disconnect", { method: "POST" });
      await load();
    } finally {
      setPending(false);
    }
  }

  // On-demand only — never triggered automatically on page load or by a timer
  // (threat model, ADR 0003).
  async function syncGoogle() {
    if (syncing) return;
    setSyncing(true);
    setSyncError(null);
    setSyncResult(null);
    try {
      const result = await api<GoogleSyncResult>("/connected-accounts/google/sync", {
        method: "POST",
      });
      setSyncResult(result);
      await load();
    } catch (error) {
      setSyncError(syncErrorState(error));
    } finally {
      setSyncing(false);
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
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-10 px-6 py-12">
      <header className="flex flex-col gap-3">
        <Link href="/today" className="text-sm underline">
          ← Back to Today
        </Link>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Privacy &amp; Connections</h1>
          <p className="mt-2 max-w-2xl" data-testid="privacy-overview">
            One place to see what LifeFlow is connected to, exactly what access you granted, what it
            has stored, and how long it is ordinarily kept. Everything here is read-only — LifeFlow
            never sends email, never changes your calendar, and never deletes anything on this page.
          </p>
        </div>
        <p aria-live="polite" className="text-sm opacity-70">
          {state === "loading" && "Loading your privacy summary…"}
          {state === "error" && "Could not load your privacy summary. Is the API running?"}
        </p>
      </header>

      {state === "ready" && summary ? (
        <>
          {/* 2. Connected accounts */}
          <section
            data-testid="google-connection-card"
            className="flex flex-col gap-2 rounded-lg border border-current/25 p-5"
          >
            <h2 className="font-semibold">Connected accounts</h2>
            {google ? (
              <div className="mt-1 flex flex-col gap-2 text-sm">
                <p>
                  Google — status:{" "}
                  <span data-testid="google-connection-status">{google.status}</span>
                </p>
                <div className="flex flex-wrap gap-2">
                  {google.connected ? (
                    <>
                      <button
                        type="button"
                        data-testid="sync-google-now"
                        onClick={syncGoogle}
                        disabled={syncing}
                        className="mt-1 w-fit rounded bg-foreground px-4 py-2 text-sm font-medium text-background disabled:opacity-50"
                      >
                        {syncing ? "Syncing…" : "Sync now"}
                      </button>
                      <button
                        type="button"
                        data-testid="disconnect-google"
                        onClick={disconnectGoogle}
                        disabled={pending}
                        className="mt-1 w-fit rounded border border-current/30 px-4 py-2 text-sm disabled:opacity-50"
                      >
                        {pending ? "Disconnecting…" : "Disconnect Google"}
                      </button>
                    </>
                  ) : (
                    <a
                      href={`${API_URL}/connected-accounts/google/connect`}
                      className="mt-1 w-fit rounded bg-foreground px-4 py-2 text-sm font-medium text-background"
                    >
                      Connect Google
                    </a>
                  )}
                </div>
                {syncError ? (
                  syncError.retryable === true ? (
                    <p
                      role="status"
                      data-testid="sync-degraded-notice"
                      className="rounded bg-amber-100 p-2 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200"
                    >
                      {syncError.message} It is safe to try syncing again in a moment.
                    </p>
                  ) : (
                    <p
                      role="alert"
                      data-testid="sync-error-notice"
                      className="text-red-700 dark:text-red-400"
                    >
                      {syncError.message}
                      {syncError.retryable === false
                        ? " Retrying now will not help — reconnect Google if this continues."
                        : ""}
                    </p>
                  )
                ) : null}
                {syncResult ? (
                  <div data-testid="sync-result" className="rounded border border-current/20 p-3">
                    <p>
                      Imported {syncResult.imported}, updated {syncResult.updated}, unchanged{" "}
                      {syncResult.unchanged}.
                    </p>
                    {syncResult.gmail_excluded > 0 ? (
                      <p data-testid="gmail-excluded-notice" className="opacity-70">
                        {syncResult.gmail_excluded} Gmail message
                        {syncResult.gmail_excluded === 1 ? "" : "s"} outside Inbox/Sent{" "}
                        {syncResult.gmail_excluded === 1 ? "was" : "were"} not imported — by design,
                        only Inbox and Sent are read.
                      </p>
                    ) : null}
                    {syncResult.gmail_incomplete > 0 ? (
                      <p
                        role="alert"
                        data-testid="gmail-incomplete-notice"
                        className="text-amber-700 dark:text-amber-400"
                      >
                        {syncResult.gmail_incomplete} Gmail message
                        {syncResult.gmail_incomplete === 1 ? "" : "s"} could not be read fully.
                      </p>
                    ) : null}
                    {syncResult.calendar_incomplete > 0 ? (
                      <p
                        role="alert"
                        data-testid="calendar-incomplete-notice"
                        className="text-amber-700 dark:text-amber-400"
                      >
                        {syncResult.calendar_incomplete} calendar event
                        {syncResult.calendar_incomplete === 1 ? "" : "s"} could not be read fully.
                      </p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="mt-1 flex flex-col gap-2 text-sm">
                <p className="opacity-70">Not connected.</p>
                <a
                  href={`${API_URL}/connected-accounts/google/connect`}
                  className="mt-1 w-fit rounded bg-foreground px-4 py-2 text-sm font-medium text-background"
                >
                  Connect Google
                </a>
              </div>
            )}
          </section>

          {/* 3. Granted access */}
          <section data-testid="granted-access" className="flex flex-col gap-2">
            <h2 className="font-semibold">Granted access</h2>
            {google && google.granted_scopes.length > 0 ? (
              <>
                <ul className="flex flex-col gap-1 text-sm">
                  {google.granted_scopes.map((scope) => (
                    <li key={scope.scope}>{scope.label}</li>
                  ))}
                </ul>
                <details data-testid="scope-technical-details" className="text-sm">
                  <summary className="cursor-pointer opacity-70">Technical detail</summary>
                  <ul className="mt-1 flex flex-col gap-1 font-mono text-xs opacity-80">
                    {google.granted_scopes.map((scope) => (
                      <li key={scope.scope}>{scope.scope}</li>
                    ))}
                  </ul>
                </details>
              </>
            ) : (
              <p className="text-sm opacity-70">No access granted.</p>
            )}
          </section>

          {/* 4. Evidence freshness */}
          <section data-testid="evidence-freshness" className="flex flex-col gap-2">
            <h2 className="font-semibold">Evidence freshness</h2>
            {google ? (
              <p className="text-sm">
                {google.ever_synced && google.freshness_band
                  ? FRESHNESS_COPY[google.freshness_band]
                  : "Never synced — no evidence has been imported yet."}
              </p>
            ) : (
              <p className="text-sm opacity-70">Connect an account to sync evidence.</p>
            )}
            <p className="text-xs opacity-60">
              Scheduled briefs only ever use evidence from a sync you started — LifeFlow never syncs
              on its own.
            </p>
          </section>

          {/* 5. Data stored by LifeFlow */}
          <section data-testid="data-inventory" className="flex flex-col gap-2">
            <h2 className="font-semibold">Data stored by LifeFlow</h2>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
              {INVENTORY_LABELS.map(({ key, label }) => (
                <div key={key} className="flex justify-between gap-2">
                  <dt className="opacity-80">{label}</dt>
                  <dd data-testid={`inventory-${key}`} className="font-medium tabular-nums">
                    {summary.inventory[key]}
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          {/* 6. Retention summary */}
          <section data-testid="retention-summary" className="flex flex-col gap-2">
            <h2 className="font-semibold">How long data is kept</h2>
            <p className="text-sm" data-testid="retention-not-enforced">
              These are provisional product defaults for the pilot, not legal requirements.{" "}
              <strong>Automatic deletion is not switched on yet</strong> — it arrives in a later
              update. Nothing here is deleted automatically today.
            </p>
            <ul className="flex flex-col gap-1 text-sm">
              {summary.retention.classes.map((cls) => (
                <li key={cls.key} className="flex justify-between gap-3">
                  <span className="opacity-80">{cls.label}</span>
                  <span className="tabular-nums opacity-70">
                    {cls.retention_days === null
                      ? "kept until reconciled / tied to its source"
                      : `${cls.retention_days} days`}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          {/* 7. Data controls — four distinct operations */}
          <section data-testid="data-controls" className="flex flex-col gap-3">
            <h2 className="font-semibold">Data controls</h2>

            <div data-testid="control-disconnect" className="rounded border border-current/20 p-4">
              <h3 className="text-sm font-semibold">Disconnect a provider</h3>
              <p className="mt-1 text-sm opacity-80">
                Revokes LifeFlow&apos;s access and stops future syncing.{" "}
                <strong>The data LifeFlow already imported stays</strong> until you delete it
                separately.
              </p>
            </div>

            <DeletionControls
              googleAccountId={google && google.connected ? google.account_id : null}
              onChanged={load}
            />

            <div
              data-testid="control-delete-memory"
              className="rounded border border-current/20 p-4"
            >
              <h3 className="text-sm font-semibold">Delete learned preferences</h3>
              <p className="mt-1 text-sm opacity-80">
                Clears what LifeFlow inferred from your own actions. It does not touch imported
                Gmail/Calendar evidence or your explicit settings.{" "}
                <Link href="/settings" data-testid="learned-preferences-link" className="underline">
                  Manage learned preferences
                </Link>
                .
              </p>
            </div>
          </section>

          {/* 8. Links out */}
          <section className="flex flex-wrap gap-4 text-sm">
            <Link href="/audit-history" data-testid="audit-history-link" className="underline">
              View audit history
            </Link>
            <Link href="/settings" data-testid="preferences-link" className="underline">
              Explicit preferences
            </Link>
            <Link href="/settings" data-testid="settings-link" className="underline">
              Learned preferences
            </Link>
          </section>
        </>
      ) : null}
    </main>
  );
}
