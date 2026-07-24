"use client";

// Stage 9 Delivery Phase 2: the actionable deletion controls (ADR 0005 §14).
// Preview → exact typed confirmation → durable progress, for imported-data
// deletion (per connected account) and account deletion (high-risk). Every
// destructive request is owner-scoped and content-free; the UI shows counts,
// preserved records, and truthful terminal states. Disconnect and delete stay
// separate; nothing here runs on page load.

import { useCallback, useEffect, useRef, useState } from "react";

import { rateLimitMessage } from "@/components/RateLimitNotice";
import { api, ApiError, RateLimitError } from "@/lib/api";
import type { DeletionOperation } from "@/lib/types";

const TERMINAL = new Set(["succeeded", "partially_failed", "failed", "cancelled"]);
const IN_PROGRESS = new Set(["pending", "running"]);

// Human labels for the count keys the engine emits (content-free).
const COUNT_LABELS: Record<string, string> = {
  source_items: "Imported emails & events",
  signals: "Detected signals",
  action_proposals: "Action proposals",
  briefs: "Daily brief versions",
  scheduled_brief_runs: "Scheduled brief runs",
  preferences: "Explicit preferences",
  memory_items: "Learned-preference items",
  memory_evidence: "Learned-preference evidence",
  connected_accounts: "Connected accounts",
  minimised_proposal_history: "Approved/executed history (kept, minimised)",
  preserved_pending_uncertain_executions: "Unresolved outcomes (always preserved)",
  minimised_proposal_tombstones: "Approved/executed history (kept, minimised)",
  retained_execution_tombstones: "Execution records (kept, content-free)",
  retained_audit_tombstones: "Audit records (kept, content-free)",
  source_reference_removed: "Records with a deleted-source reference removed",
};

function countList(counts: Record<string, number>): Array<[string, number]> {
  return Object.entries(counts).filter(([, n]) => n > 0);
}

function StatusLine({ operation }: { operation: DeletionOperation }) {
  let text = "";
  if (operation.state === "pending") text = "Queued — deletion will begin shortly.";
  else if (operation.state === "running") text = "Deleting…";
  else if (operation.state === "succeeded") text = "Done. The data has been deleted.";
  else if (operation.state === "cancelled") text = "Cancelled. Nothing was deleted.";
  else if (operation.state === "partially_failed")
    text = "Mostly done — some steps could not finish. Your data was still erased.";
  else if (operation.state === "failed") text = "This could not be completed.";
  return (
    <p data-testid="operation-status" role="status" aria-live="polite" className="text-sm">
      {text}
    </p>
  );
}

function CountBlock({
  title,
  counts,
  testid,
}: {
  title: string;
  counts: Record<string, number>;
  testid: string;
}) {
  const rows = countList(counts);
  if (rows.length === 0) return null;
  return (
    <div data-testid={testid} className="text-sm">
      <p className="font-medium">{title}</p>
      <ul className="mt-1 flex flex-col gap-0.5">
        {rows.map(([key, n]) => (
          <li key={key} className="flex justify-between gap-3">
            <span className="opacity-80">{COUNT_LABELS[key] ?? key}</span>
            <span className="tabular-nums opacity-70">{n}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DeletionFlow({
  testidPrefix,
  title,
  description,
  highRisk,
  previewPath,
  onTerminalSuccess,
}: {
  testidPrefix: string;
  title: string;
  description: React.ReactNode;
  highRisk: boolean;
  previewPath: string;
  onTerminalSuccess: () => void;
}) {
  const [operation, setOperation] = useState<DeletionOperation | null>(null);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const notifiedTerminal = useRef(false);

  const preview = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const op = await api<DeletionOperation>(previewPath, { method: "POST" });
      setOperation(op);
      setTyped("");
      notifiedTerminal.current = false;
    } catch (err) {
      if (err instanceof RateLimitError) {
        // No preview/operation was created — the button stays available.
        setError(rateLimitMessage(err.retryAfterSeconds));
      } else {
        setError(err instanceof ApiError ? err.message : "Could not build the preview.");
      }
    } finally {
      setBusy(false);
    }
  }, [busy, previewPath]);

  const confirm = useCallback(async () => {
    // Guard against a double-click creating two requests: `busy` blocks the
    // second, and the exact-phrase requirement blocks an accidental submit.
    if (busy || !operation) return;
    if (typed !== operation.confirmation_phrase) return;
    setBusy(true);
    setError("");
    try {
      const op = await api<DeletionOperation>(
        `/privacy/deletion-operations/${operation.operation_id}/confirm`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_version: operation.version,
            confirmation_phrase: typed,
          }),
        },
      );
      setOperation(op);
    } catch (err) {
      if (err instanceof RateLimitError) {
        // The reviewed preview, its fingerprint/version, and the typed
        // phrase are all left exactly as they were — safe for a manual retry.
        setError(rateLimitMessage(err.retryAfterSeconds));
      } else {
        setError(err instanceof ApiError ? err.message : "Could not confirm.");
      }
    } finally {
      setBusy(false);
    }
  }, [busy, operation, typed]);

  const cancel = useCallback(async () => {
    if (busy || !operation) return;
    setBusy(true);
    try {
      const op = await api<DeletionOperation>(
        `/privacy/deletion-operations/${operation.operation_id}/cancel`,
        { method: "POST" },
      );
      setOperation(op);
    } catch (err) {
      if (err instanceof RateLimitError) {
        setError(rateLimitMessage(err.retryAfterSeconds));
      } else {
        setError(err instanceof ApiError ? err.message : "Could not cancel.");
      }
    } finally {
      setBusy(false);
    }
  }, [busy, operation]);

  // Poll durable progress while the operation is queued or running.
  useEffect(() => {
    if (!operation || !IN_PROGRESS.has(operation.state)) return;
    const id = operation.operation_id;
    const timer = setInterval(async () => {
      try {
        const op = await api<DeletionOperation>(`/privacy/deletion-operations/${id}`);
        setOperation(op);
      } catch (err) {
        // A 401 while polling means the session was invalidated — for account
        // deletion this is the completion signal. Stop polling (never loop on
        // repeated 401s) and go to the signed-out experience.
        if (err instanceof ApiError && err.status === 401) {
          clearInterval(timer);
          window.location.assign("/");
          return;
        }
        /* other errors are transient; keep polling */
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [operation]);

  // Notify the parent exactly once when a deletion completes successfully.
  useEffect(() => {
    if (!operation || notifiedTerminal.current) return;
    if (operation.state === "succeeded" || operation.state === "partially_failed") {
      notifiedTerminal.current = true;
      onTerminalSuccess();
    }
  }, [operation, onTerminalSuccess]);

  const previewing = operation !== null && operation.state === "previewed";
  const terminal = operation !== null && TERMINAL.has(operation.state);
  const phraseMatches = operation !== null && typed === operation.confirmation_phrase;

  return (
    <div
      data-testid={`${testidPrefix}-control`}
      className={`rounded border p-4 ${highRisk ? "border-red-600/60" : "border-current/20"}`}
    >
      <h3 className="text-sm font-semibold">{title}</h3>
      <div className="mt-1 text-sm opacity-80">{description}</div>

      {error ? (
        <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      ) : null}

      {operation === null ? (
        <button
          type="button"
          data-testid={`${testidPrefix}-preview`}
          onClick={preview}
          disabled={busy}
          className="mt-3 w-fit rounded border border-current/30 px-4 py-2 text-sm disabled:opacity-50"
        >
          {busy ? "Preparing…" : "Preview what will be deleted"}
        </button>
      ) : null}

      {previewing ? (
        <div className="mt-3 flex flex-col gap-3">
          <CountBlock
            title="Will be deleted"
            counts={operation.preview_counts}
            testid={`${testidPrefix}-preview-counts`}
          />
          <CountBlock
            title="Will be kept (content-free)"
            counts={operation.preserved_counts}
            testid={`${testidPrefix}-preserved-counts`}
          />
          {operation.warnings.length > 0 ? (
            <ul data-testid={`${testidPrefix}-warnings`} className="flex flex-col gap-1 text-sm">
              {operation.warnings.map((w) => (
                <li key={w} className="opacity-80">
                  • {w}
                </li>
              ))}
            </ul>
          ) : null}
          <label className="flex flex-col gap-1 text-sm">
            <span>
              Type <strong>{operation.confirmation_phrase}</strong> to confirm.
            </span>
            <input
              data-testid={`${testidPrefix}-confirm-input`}
              type="text"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              aria-label={`Type ${operation.confirmation_phrase} to confirm`}
              className="w-full rounded border border-current/30 bg-transparent px-3 py-2"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              data-testid={`${testidPrefix}-confirm`}
              onClick={confirm}
              disabled={busy || !phraseMatches}
              className={`w-fit rounded px-4 py-2 text-sm font-medium disabled:opacity-40 ${
                highRisk ? "bg-red-700 text-white" : "bg-foreground text-background"
              }`}
            >
              {busy ? "Working…" : "Delete permanently"}
            </button>
            <button
              type="button"
              data-testid={`${testidPrefix}-cancel`}
              onClick={cancel}
              disabled={busy}
              className="w-fit rounded border border-current/30 px-4 py-2 text-sm disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {operation !== null && (IN_PROGRESS.has(operation.state) || terminal) ? (
        <div className="mt-3 flex flex-col gap-2">
          <StatusLine operation={operation} />
          <CountBlock
            title="Deleted so far"
            counts={operation.deleted_counts}
            testid={`${testidPrefix}-deleted-counts`}
          />
        </div>
      ) : null}
    </div>
  );
}

export default function DeletionControls({
  googleAccountId,
  onChanged,
}: {
  googleAccountId: string | null;
  onChanged: () => void;
}) {
  const handleAccountDeleted = useCallback(() => {
    // The account is anonymised; existing sessions stop working. Reset the
    // client to the signed-out experience.
    window.location.assign("/");
  }, []);

  return (
    <>
      {googleAccountId ? (
        <DeletionFlow
          testidPrefix="delete-imported"
          title="Delete imported provider data"
          description={
            <span>
              Removes LifeFlow&apos;s imported copy and eligible derived data for this account. It{" "}
              <strong>never deletes anything in your Gmail or Google Calendar</strong>. For a
              complete clean-out, disconnect first — this never disconnects for you.
            </span>
          }
          highRisk={false}
          previewPath={`/privacy/imported-data/${googleAccountId}/preview`}
          onTerminalSuccess={onChanged}
        />
      ) : (
        <div
          data-testid="delete-imported-unavailable"
          className="rounded border border-current/20 p-4 text-sm opacity-70"
        >
          Connect and sync an account to enable imported-data deletion.
        </div>
      )}

      <DeletionFlow
        testidPrefix="delete-account"
        title="Delete the LifeFlow account"
        description={
          <span>
            Revokes connections and removes your personal product data, keeping only
            privacy-minimised, content-free records needed for integrity. It{" "}
            <strong>never deletes your Gmail or Google account</strong>, and it cannot be undone.
          </span>
        }
        highRisk
        previewPath="/privacy/account-deletion/preview"
        onTerminalSuccess={handleAccountDeleted}
      />
    </>
  );
}
