"use client";

// Stage 9 Privacy & Connections Control Centre. GET /privacy/summary remains
// the privacy-safe read projection; existing connection controls, Phase 2
// deletion controls, and the Phase 3 audit-history link stay distinct.

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { rateLimitMessage } from "@/components/RateLimitNotice";
import { AppShell, PageHeader } from "@/components/ui/AppShell";
import { Button } from "@/components/ui/Button";
import { FormSection } from "@/components/ui/Form";
import { Notice } from "@/components/ui/Notice";
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
    <AppShell>
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-8 sm:px-6 sm:py-10">
        <PageHeader
          title="Privacy & Connections"
          description={
            <>
              <span data-testid="privacy-overview" className="block">
                One place to see what LifeFlow is connected to, exactly what access you granted,
                what it has stored, and how long it is ordinarily kept. Everything here is read-only
                — LifeFlow never sends email, never changes your calendar, and never deletes
                anything on this page.
              </span>
              <span aria-live="polite" className="mt-2 block">
                {state === "loading" && "Loading your privacy summary…"}
                {state === "error" && "Could not load your privacy summary. Is the API running?"}
              </span>
            </>
          }
        />

        {state === "ready" && summary ? (
          <>
            {/* 2. Connected accounts */}
            <FormSection legend="Connected accounts">
              <div data-testid="google-connection-card" className="contents">
                {google ? (
                  <div className="flex flex-col gap-3 text-sm">
                    <p className="text-text-secondary">
                      Google — status:{" "}
                      <span
                        data-testid="google-connection-status"
                        className="font-medium text-foreground"
                      >
                        {google.status}
                      </span>
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {google.connected ? (
                        <>
                          <Button
                            type="button"
                            variant="primary"
                            data-testid="sync-google-now"
                            onClick={syncGoogle}
                            disabled={syncing}
                          >
                            {syncing ? "Syncing…" : "Sync now"}
                          </Button>
                          <Button
                            type="button"
                            variant="secondary"
                            data-testid="disconnect-google"
                            onClick={disconnectGoogle}
                            disabled={pending}
                          >
                            {pending ? "Disconnecting…" : "Disconnect Google"}
                          </Button>
                        </>
                      ) : (
                        <a
                          href={`${API_URL}/connected-accounts/google/connect`}
                          className="inline-flex w-fit items-center justify-center rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
                        >
                          Connect Google
                        </a>
                      )}
                    </div>
                    {syncError ? (
                      syncError.retryable === true ? (
                        <Notice tone="warning" role="status" testId="sync-degraded-notice">
                          {syncError.message} It is safe to try syncing again in a moment.
                        </Notice>
                      ) : (
                        <Notice tone="danger" role="alert" testId="sync-error-notice">
                          {syncError.message}
                          {syncError.retryable === false
                            ? " Retrying now will not help — reconnect Google if this continues."
                            : ""}
                        </Notice>
                      )
                    ) : null}
                    {syncResult ? (
                      <div
                        data-testid="sync-result"
                        className="rounded-md border border-border bg-surface-raised p-3"
                      >
                        <p>
                          Imported {syncResult.imported}, updated {syncResult.updated}, unchanged{" "}
                          {syncResult.unchanged}.
                        </p>
                        {syncResult.gmail_excluded > 0 ? (
                          <p data-testid="gmail-excluded-notice" className="text-text-tertiary">
                            {syncResult.gmail_excluded} Gmail message
                            {syncResult.gmail_excluded === 1 ? "" : "s"} outside Inbox/Sent{" "}
                            {syncResult.gmail_excluded === 1 ? "was" : "were"} not imported — by
                            design, only Inbox and Sent are read.
                          </p>
                        ) : null}
                        {syncResult.gmail_incomplete > 0 ? (
                          <p
                            role="alert"
                            data-testid="gmail-incomplete-notice"
                            className="text-warning-text"
                          >
                            {syncResult.gmail_incomplete} Gmail message
                            {syncResult.gmail_incomplete === 1 ? "" : "s"} could not be read fully.
                          </p>
                        ) : null}
                        {syncResult.calendar_incomplete > 0 ? (
                          <p
                            role="alert"
                            data-testid="calendar-incomplete-notice"
                            className="text-warning-text"
                          >
                            {syncResult.calendar_incomplete} calendar event
                            {syncResult.calendar_incomplete === 1 ? "" : "s"} could not be read
                            fully.
                          </p>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <div className="flex flex-col gap-3 text-sm">
                    <p className="text-text-secondary">Not connected.</p>
                    <a
                      href={`${API_URL}/connected-accounts/google/connect`}
                      className="inline-flex w-fit items-center justify-center rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover"
                    >
                      Connect Google
                    </a>
                  </div>
                )}
              </div>
            </FormSection>

            {/* 3. Granted access */}
            <FormSection legend="Granted access" testId="granted-access">
              {google && google.granted_scopes.length > 0 ? (
                <>
                  <ul className="flex flex-col gap-1 text-sm text-text-secondary">
                    {google.granted_scopes.map((scope) => (
                      <li key={scope.scope}>{scope.label}</li>
                    ))}
                  </ul>
                  <details data-testid="scope-technical-details" className="text-sm">
                    <summary className="cursor-pointer text-text-tertiary">
                      Technical detail
                    </summary>
                    <ul className="mt-1 flex flex-col gap-1 font-mono text-xs text-text-tertiary">
                      {google.granted_scopes.map((scope) => (
                        <li key={scope.scope}>{scope.scope}</li>
                      ))}
                    </ul>
                  </details>
                </>
              ) : (
                <p className="text-sm text-text-tertiary">No access granted.</p>
              )}
            </FormSection>

            {/* 4. Evidence freshness */}
            <FormSection legend="Evidence freshness" testId="evidence-freshness">
              {google ? (
                <p className="text-sm text-text-secondary">
                  {google.ever_synced && google.freshness_band
                    ? FRESHNESS_COPY[google.freshness_band]
                    : "Never synced — no evidence has been imported yet."}
                </p>
              ) : (
                <p className="text-sm text-text-tertiary">Connect an account to sync evidence.</p>
              )}
              <p className="text-xs text-text-tertiary">
                Scheduled briefs only ever use evidence from a sync you started — LifeFlow never
                syncs on its own.
              </p>
            </FormSection>

            {/* 5. Data stored by LifeFlow */}
            <FormSection legend="Data stored by LifeFlow" testId="data-inventory">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
                {INVENTORY_LABELS.map(({ key, label }) => (
                  <div key={key} className="flex justify-between gap-2">
                    <dt className="text-text-secondary">{label}</dt>
                    <dd
                      data-testid={`inventory-${key}`}
                      className="font-medium text-foreground tabular-nums"
                    >
                      {summary.inventory[key]}
                    </dd>
                  </div>
                ))}
              </dl>
            </FormSection>

            {/* 6. Retention summary */}
            <FormSection legend="How long data is kept" testId="retention-summary">
              <p className="text-sm text-text-secondary" data-testid="retention-not-enforced">
                These are provisional product defaults for the pilot, not legal requirements.{" "}
                <strong className="text-foreground">
                  Automatic deletion is not switched on yet
                </strong>{" "}
                — it arrives in a later update. Nothing here is deleted automatically today.
              </p>
              <ul className="flex flex-col gap-1 text-sm">
                {summary.retention.classes.map((cls) => (
                  <li key={cls.key} className="flex justify-between gap-3">
                    <span className="text-text-secondary">{cls.label}</span>
                    <span className="text-text-tertiary tabular-nums">
                      {cls.retention_days === null
                        ? "kept until reconciled / tied to its source"
                        : `${cls.retention_days} days`}
                    </span>
                  </li>
                ))}
              </ul>
            </FormSection>

            {/* 7. Data controls — four distinct operations */}
            <FormSection
              legend="Data controls"
              description="Disconnecting, deleting imported data, and deleting your account are separate operations with separate consequences — each is explained before you act."
              testId="data-controls"
            >
              <div data-testid="control-disconnect" className="rounded-md border border-border p-4">
                <h3 className="text-sm font-semibold text-foreground">Disconnect a provider</h3>
                <p className="mt-1 text-sm text-text-secondary">
                  Revokes LifeFlow&apos;s access and stops future syncing.{" "}
                  <strong className="text-foreground">
                    The data LifeFlow already imported stays
                  </strong>{" "}
                  until you delete it separately.
                </p>
              </div>

              <DeletionControls
                googleAccountId={google && google.connected ? google.account_id : null}
                onChanged={load}
              />

              <div
                data-testid="control-delete-memory"
                className="rounded-md border border-border p-4"
              >
                <h3 className="text-sm font-semibold text-foreground">
                  Delete learned preferences
                </h3>
                <p className="mt-1 text-sm text-text-secondary">
                  Clears what LifeFlow inferred from your own actions. It does not touch imported
                  Gmail/Calendar evidence or your explicit settings.{" "}
                  <Link
                    href="/settings"
                    data-testid="learned-preferences-link"
                    className="text-accent underline"
                  >
                    Manage learned preferences
                  </Link>
                  .
                </p>
              </div>
            </FormSection>

            {/* 8. Links out */}
            <section className="flex flex-wrap gap-4 text-sm">
              <Link
                href="/audit-history"
                data-testid="audit-history-link"
                className="text-accent underline"
              >
                View audit history
              </Link>
              <Link
                href="/settings"
                data-testid="preferences-link"
                className="text-accent underline"
              >
                Explicit preferences
              </Link>
              <Link
                href="/settings"
                data-testid="learned-preferences-footer-link"
                className="text-accent underline"
              >
                Learned preferences
              </Link>
            </section>
          </>
        ) : null}
      </div>
    </AppShell>
  );
}
