"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { API_URL, api, ApiError } from "@/lib/api";
import type { ConnectedAccount, ConnectedAccountsResponse, GoogleSyncResult } from "@/lib/types";

type LoadState = "loading" | "ready" | "unauthenticated" | "error";

export default function ConnectionsPage() {
  const [state, setState] = useState<LoadState>("loading");
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [pending, setPending] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<GoogleSyncResult | null>(null);
  const [syncError, setSyncError] = useState("");

  const load = useCallback(async () => {
    try {
      const response = await api<ConnectedAccountsResponse>("/connected-accounts");
      setAccounts(response.accounts);
      setState("ready");
    } catch (error) {
      setState(error instanceof ApiError && error.status === 401 ? "unauthenticated" : "error");
    }
  }, []);

  useEffect(() => {
    // State changes occur only after the external API promise settles.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  const google = accounts.find((account) => account.provider === "google");

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

  // On-demand only — never triggered automatically on page load or by a
  // timer, so a connected account never causes background Google traffic
  // the user didn't ask for (threat model, ADR 0003).
  async function syncGoogle() {
    if (syncing) return;
    setSyncing(true);
    setSyncError("");
    setSyncResult(null);
    try {
      const result = await api<GoogleSyncResult>("/connected-accounts/google/sync", {
        method: "POST",
      });
      setSyncResult(result);
      await load();
    } catch (error) {
      setSyncError(error instanceof ApiError ? error.message : "Google sync could not complete.");
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
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col gap-8 px-6 py-12">
      <header className="flex flex-col gap-3">
        <Link href="/today" className="text-sm underline">
          ← Back to Today
        </Link>
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Connections</h1>
          <p className="mt-2 max-w-2xl">
            Connecting Google is separate from signing in — it only requests read access to Gmail
            and Calendar, plus the ability to create drafts and calendar events after your approval.
            Disconnecting stops all further syncing immediately.
          </p>
        </div>
        <p aria-live="polite" className="text-sm opacity-70">
          {state === "loading" && "Loading connections…"}
          {state === "error" && "Could not load connections. Is the API running?"}
        </p>
      </header>

      {state === "ready" ? (
        <section
          data-testid="google-connection-card"
          className="rounded-lg border border-current/25 p-5"
        >
          <h2 className="font-semibold">Google</h2>
          {google ? (
            <div className="mt-2 flex flex-col gap-2 text-sm">
              <p>
                Status: <span data-testid="google-connection-status">{google.status}</span>
              </p>
              <p>
                Granted scopes:{" "}
                {google.granted_scopes.length ? google.granted_scopes.join(", ") : "none"}
              </p>
              <p>Last sync: {google.last_sync_at ?? "never"}</p>
              <div className="flex flex-wrap gap-2">
                {google.status === "active" ? (
                  <>
                    <button
                      type="button"
                      data-testid="sync-google-now"
                      onClick={syncGoogle}
                      disabled={syncing}
                      className="mt-2 w-fit rounded bg-foreground px-4 py-2 text-sm font-medium text-background disabled:opacity-50"
                    >
                      {syncing ? "Syncing…" : "Sync now"}
                    </button>
                    <button
                      type="button"
                      onClick={disconnectGoogle}
                      disabled={pending}
                      className="mt-2 w-fit rounded border border-current/30 px-4 py-2 text-sm disabled:opacity-50"
                    >
                      {pending ? "Disconnecting…" : "Disconnect Google"}
                    </button>
                  </>
                ) : (
                  // A disconnected/expired/revoked account keeps its history
                  // visible above (status, prior scopes, last sync) rather
                  // than hiding it — but the only useful action left is to
                  // reconnect, never a Sync/Disconnect button that can no
                  // longer do anything.
                  <a
                    href={`${API_URL}/connected-accounts/google/connect`}
                    className="mt-2 w-fit rounded bg-foreground px-4 py-2 text-sm font-medium text-background"
                  >
                    Connect Google
                  </a>
                )}
              </div>
              {syncError ? (
                <p role="alert" className="text-red-700 dark:text-red-400">
                  {syncError}
                </p>
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
                  <p className="opacity-70">
                    Gmail:{" "}
                    {syncResult.gmail_synced ? syncResult.gmail_cursor_status : "not granted"} ·
                    Calendar:{" "}
                    {syncResult.calendar_synced ? syncResult.calendar_cursor_status : "not granted"}
                  </p>
                  <p className="mt-1">
                    <Link href="/today" className="underline">
                      Go to Today
                    </Link>{" "}
                    to generate a brief from this data.
                  </p>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="mt-2 flex flex-col gap-2 text-sm">
              <p className="opacity-70">Not connected.</p>
              <a
                href={`${API_URL}/connected-accounts/google/connect`}
                className="mt-2 w-fit rounded bg-foreground px-4 py-2 text-sm font-medium text-background"
              >
                Connect Google
              </a>
            </div>
          )}
        </section>
      ) : null}
    </main>
  );
}
