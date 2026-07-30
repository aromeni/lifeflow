"use client";

import { useMemo, useState } from "react";

import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { rateLimitMessage } from "@/components/RateLimitNotice";
import { Badge, RiskBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { api, ApiError, RateLimitError } from "@/lib/api";
import type { ActionPayload, ActionProposal } from "@/lib/types";

const ACTION_LABELS: Record<ActionProposal["action_type"], string> = {
  create_task: "Create internal task",
  create_gmail_draft: "Create Gmail draft",
  create_calendar_event: "Create calendar event",
};

const TERMINAL_STATUSES = new Set<ActionProposal["status"]>([
  "rejected",
  "executed",
  "failed",
  "expired",
]);

function formatDate(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(iso));
}

function formatFieldName(name: string): string {
  return name.replaceAll("_", " ").replace(/^./, (character) => character.toUpperCase());
}

function formatValue(value: unknown, timezone: string): string {
  if (value === null) return "None";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return formatDate(value, timezone);
  }
  return String(value);
}

// A real action must never be presented as simulated, and a simulated
// action must never be presented as real (independent-review blocker #1/#4)
// — every string here is driven by `execution_mode` from the API, never
// assumed. Raw internal identifiers (connected/source account IDs) are
// never exposed here — the API itself omits them from `execution_context`.
function executionModeNotice(proposal: ActionProposal): { title: string; body: string } {
  if (proposal.execution_mode === "unavailable") {
    return {
      title: "Unavailable — cannot approve or execute",
      body: "Connect a Google account with the right permission, or use demo mode, before this can be approved.",
    };
  }
  if (proposal.execution_mode === "simulation") {
    return {
      title: "Simulation — no external system will change",
      body: "This action will be simulated. No external service will be changed.",
    };
  }
  if (proposal.action_type === "create_gmail_draft") {
    return {
      title: "Real Gmail — creates a draft, does not send it",
      body: "This will create a real draft in your connected Gmail account. It will not send the email.",
    };
  }
  return {
    title: "Real Calendar — creates an event, guest notifications off",
    body: "This will create a real event in your connected Google Calendar. Guest notifications are off.",
  };
}

function executionResultHeading(proposal: ActionProposal): string {
  const execution = proposal.execution;
  if (!execution) return "";
  if (execution.effective_status === "uncertain") {
    return "Outcome uncertain — not retried automatically";
  }
  if (execution.effective_status === "failed") {
    if (execution.error_code === "approval_context_changed") {
      return "Not executed — approval context changed";
    }
    return execution.execution_mode === "real" ? "Execution failed" : "Simulation failed";
  }
  if (execution.execution_mode === "real") {
    return proposal.action_type === "create_gmail_draft"
      ? "Gmail draft created"
      : "Calendar event created";
  }
  return "Simulation result";
}

// The proposal's own `status` stays the internal `"executing"` state for
// the entire time an execution's outcome is uncertain (D16 — deliberately
// not a new status value) — but showing that raw word as the dominant,
// top-of-card label reads as "still in progress", not "we don't know what
// happened". A real sandbox execution surfaced this as confusing: the
// badge must say plainly that the outcome is uncertain, not just repeat
// the internal in-flight state.
function proposalStatusLabel(proposal: ActionProposal): string {
  if (proposal.execution?.effective_status === "uncertain") {
    return "Execution outcome uncertain";
  }
  return proposal.status;
}

export function ExactPayloadPreview({
  actionType,
  version,
  payload,
  payloadHash,
  timezone,
  testId,
}: {
  actionType: ActionProposal["action_type"];
  version: number;
  payload: ActionPayload;
  payloadHash: string;
  timezone: string;
  testId: string;
}) {
  return (
    <section
      aria-label="Exact approval preview"
      data-testid={testId}
      className="flex flex-col gap-3 rounded-lg border-2 border-accent/30 bg-accent-subtle/20 p-4"
    >
      <div>
        <h3 className="font-semibold text-foreground">Exact approval preview</h3>
        <p className="text-sm text-text-secondary">
          {ACTION_LABELS[actionType]} · proposal version {version}
        </p>
      </div>
      <dl className="grid gap-2 text-sm sm:grid-cols-[10rem_1fr]">
        {Object.entries(payload).map(([name, value]) => (
          <div key={name} className="contents">
            <dt className="font-medium text-foreground">{formatFieldName(name)}</dt>
            <dd className="wrap-break-word whitespace-pre-wrap text-text-secondary">
              {formatValue(value, timezone)}
            </dd>
          </div>
        ))}
      </dl>
      <details className="text-xs">
        <summary className="cursor-pointer text-text-secondary underline">
          Exact canonical JSON and hash
        </summary>
        <pre className="mt-2 overflow-x-auto rounded-md bg-surface-raised p-3 whitespace-pre-wrap break-all">
          {JSON.stringify({ action_type: actionType, proposal_version: version, payload }, null, 2)}
        </pre>
        <p className="mt-2 font-mono break-all text-text-tertiary">
          Payload SHA-256: {payloadHash}
        </p>
      </details>
    </section>
  );
}

const STATUS_TONE: Record<string, "neutral" | "info" | "success" | "warning" | "danger"> = {
  proposed: "neutral",
  edited: "neutral",
  approved: "info",
  executing: "info",
  executed: "success",
  rejected: "neutral",
  failed: "danger",
  expired: "neutral",
  "execution outcome uncertain": "warning",
};

export function ActionProposalPanel({
  proposal,
  timezone,
  onChanged,
}: {
  proposal: ActionProposal;
  timezone: string;
  onChanged: (proposal: ActionProposal) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => JSON.stringify(proposal.payload, null, 2));
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState("");
  const terminal = TERMINAL_STATUSES.has(proposal.status);
  const canEdit = ["proposed", "edited", "approved"].includes(proposal.status);
  const canApprove =
    ["proposed", "edited"].includes(proposal.status) && proposal.execution_mode !== "unavailable";
  const canReject = ["proposed", "edited", "approved"].includes(proposal.status);
  const exactJson = useMemo(() => JSON.stringify(proposal.payload, null, 2), [proposal.payload]);

  async function transition(label: string, path: string, body?: object) {
    if (pending) return;
    setPending(label);
    setError("");
    try {
      const changed = await api<ActionProposal>(path, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      onChanged(changed);
      setDraft(JSON.stringify(changed.payload, null, 2));
      setEditing(false);
    } catch (caught) {
      if (caught instanceof RateLimitError) {
        // Distinct from a provider failure or an uncertain outcome — the
        // request never reached the proposal service. Form/editor state,
        // and the proposal's own status, are left exactly as they were.
        setError(rateLimitMessage(caught.retryAfterSeconds));
      } else {
        setError(
          caught instanceof ApiError ? caught.message : "The proposal could not be updated.",
        );
      }
    } finally {
      setPending(null);
    }
  }

  async function saveEdit() {
    if (pending) return;
    setError("");
    let payload: ActionPayload;
    try {
      payload = JSON.parse(draft) as ActionPayload;
    } catch {
      setError("The payload must be valid JSON.");
      return;
    }
    setPending("edit");
    try {
      const changed = await api<ActionProposal>(`/action-proposals/${proposal.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          expected_version: proposal.version,
          action_type: proposal.action_type,
          payload,
        }),
      });
      onChanged(changed);
      setDraft(JSON.stringify(changed.payload, null, 2));
      setEditing(false);
    } catch (caught) {
      if (caught instanceof RateLimitError) {
        setError(rateLimitMessage(caught.retryAfterSeconds));
      } else {
        setError(caught instanceof ApiError ? caught.message : "The proposal could not be edited.");
      }
    } finally {
      setPending(null);
    }
  }

  const statusLabel = proposalStatusLabel(proposal);
  const statusTone = STATUS_TONE[statusLabel.toLowerCase()] ?? "neutral";

  return (
    <article
      data-testid={`proposal-${proposal.action_type}`}
      className="flex flex-col gap-5 rounded-lg border border-border bg-surface p-5 shadow-sm"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2 className="text-xl font-semibold text-foreground">
            {ACTION_LABELS[proposal.action_type]}
          </h2>
          <p className="text-text-secondary">{proposal.rationale}</p>
        </div>
        <Badge tone={statusTone} testId={`proposal-status-${proposal.action_type}`}>
          {statusLabel}
        </Badge>
      </header>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-text-secondary">
        <RiskBadge level={proposal.risk_level} />
        <span>Confidence: {Math.round(proposal.confidence * 100)}%</span>
        <span data-testid="proposal-expires">
          Expires: {formatDate(proposal.expires_at, timezone)}
        </span>
      </div>

      <Notice
        tone={proposal.execution_mode === "unavailable" ? "warning" : "info"}
        role="status"
        testId="execution-mode-notice"
        title={executionModeNotice(proposal).title}
      >
        {executionModeNotice(proposal).body}
      </Notice>

      <EvidenceDrawer evidence={proposal.evidence} timezone={timezone} />

      <ExactPayloadPreview
        actionType={proposal.action_type}
        version={proposal.version}
        payload={proposal.payload}
        payloadHash={proposal.payload_hash}
        timezone={timezone}
        testId={`payload-preview-${proposal.action_type}`}
      />

      {proposal.action_type === "create_calendar_event" ? (
        <Notice
          tone="info"
          role="status"
          testId="guest-notifications-notice"
          title="Guest notifications: off"
        >
          Creating this event never emails attendees an invitation and never updates their calendars
          — only your own calendar is affected.
        </Notice>
      ) : null}

      {proposal.approval ? (
        <Notice
          tone="success"
          role="status"
          testId="approval-binding"
          title="Approved exact payload"
        >
          <p>
            Version {proposal.approval.proposal_version} · approved{" "}
            {formatDate(proposal.approval.approved_at, timezone)}
          </p>
          <p className="mt-1">
            Approved execution context: {proposal.approval.execution_context.mode}
            {proposal.approval.execution_context.provider === "google"
              ? " (Google)"
              : " (simulation)"}
          </p>
          <p className="mt-1 font-mono text-xs break-all">
            Binding SHA-256: {proposal.approval.binding_hash}
          </p>
        </Notice>
      ) : null}

      {proposal.execution_context_changed ? (
        <Notice
          tone="warning"
          role="alert"
          testId="execution-context-changed-notice"
          title="Execution context changed since approval"
        >
          What this action would actually do has changed since it was approved (for example, the
          connected Google account changed). Reload and review it again before approving or
          executing.
        </Notice>
      ) : null}

      {editing ? (
        <section className="flex flex-col gap-2">
          <label htmlFor={`payload-${proposal.id}`} className="font-medium text-foreground">
            Edit every executor input field
          </label>
          <p className="text-sm text-text-secondary">
            Saving increments the proposal version. If this proposal was approved, saving also
            invalidates that approval and requires a fresh review.
          </p>
          <textarea
            id={`payload-${proposal.id}`}
            data-testid={`payload-editor-${proposal.action_type}`}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={12}
            spellCheck={false}
            className="w-full rounded-md border border-border-strong bg-surface p-3 font-mono text-sm text-foreground"
          />
          <div className="flex gap-2">
            <Button type="button" variant="primary" onClick={saveEdit} disabled={pending !== null}>
              {pending === "edit" ? "Saving…" : "Save and invalidate approval"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setDraft(exactJson);
                setEditing(false);
                setError("");
              }}
              disabled={pending !== null}
            >
              Cancel
            </Button>
          </div>
        </section>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {canApprove ? (
          <Button
            type="button"
            variant="primary"
            data-testid={`approve-${proposal.action_type}`}
            onClick={() =>
              transition("approve", `/action-proposals/${proposal.id}/approve`, {
                expected_version: proposal.version,
                action_type: proposal.action_type,
                displayed_payload_hash: proposal.payload_hash,
                displayed_execution_context_hash: proposal.execution_context_hash,
              })
            }
            disabled={pending !== null}
          >
            {pending === "approve" ? "Approving…" : "Approve exact payload"}
          </Button>
        ) : null}
        {proposal.status === "approved" ? (
          <Button
            type="button"
            variant="primary"
            data-testid={`execute-${proposal.action_type}`}
            onClick={() => transition("execute", `/action-proposals/${proposal.id}/execute`)}
            disabled={pending !== null || proposal.execution_context_changed}
          >
            {proposal.execution_mode === "real"
              ? pending === "execute"
                ? "Executing…"
                : "Execute approved action"
              : pending === "execute"
                ? "Simulating…"
                : "Run approved simulation"}
          </Button>
        ) : null}
        {canEdit && !editing ? (
          <Button
            type="button"
            variant="secondary"
            onClick={() => setEditing(true)}
            disabled={pending !== null}
          >
            Edit exact payload
          </Button>
        ) : null}
        {canReject ? (
          <Button
            type="button"
            variant="secondary"
            data-testid={`reject-${proposal.action_type}`}
            onClick={() =>
              transition("reject", `/action-proposals/${proposal.id}/reject`, {
                expected_version: proposal.version,
                reason: null,
              })
            }
            disabled={pending !== null}
          >
            {pending === "reject" ? "Rejecting…" : "Reject"}
          </Button>
        ) : null}
      </div>

      {proposal.execution ? (
        <section
          data-testid="execution-result"
          data-execution-mode={proposal.execution.execution_mode}
          className="rounded-md border border-border bg-surface-raised p-3 text-sm text-foreground"
        >
          <h3 className="font-medium">{executionResultHeading(proposal)}</h3>
          <p className="text-text-secondary">
            {proposal.execution.effective_status} · one execution record · version{" "}
            {proposal.execution.proposal_version}
          </p>
          {proposal.execution.effective_status === "uncertain" ? (
            <div className="mt-2">
              <Notice tone="warning" role="status" testId="execution-uncertain-warning">
                We could not confirm this action completed. It has not been retried automatically —
                check directly with the provider before assuming either outcome.
              </Notice>
            </div>
          ) : null}
          {proposal.execution.error_code === "approval_context_changed" ? (
            <div className="mt-2">
              <Notice tone="warning" role="status" testId="approval-context-changed-warning">
                The connected account, its authorisation, or its permission changed after you
                approved this — so no external action was attempted. This proposal cannot be
                retried. Reconnect if needed, then check your next generated brief for a fresh
                proposal.
              </Notice>
            </div>
          ) : null}
          <pre className="mt-2 overflow-x-auto text-text-secondary whitespace-pre-wrap">
            {JSON.stringify(proposal.execution.result, null, 2)}
          </pre>
        </section>
      ) : null}

      <details data-testid={`audit-trail-${proposal.action_type}`} className="text-sm">
        <summary className="cursor-pointer text-text-secondary underline">
          Audit trail ({proposal.audit_events.length} event
          {proposal.audit_events.length === 1 ? "" : "s"})
        </summary>
        {proposal.audit_events.length ? (
          <ol className="mt-2 flex flex-col gap-2 border-l-2 border-border pl-3">
            {proposal.audit_events.map((event, index) => (
              <li key={`${event.timestamp}-${event.event_type}-${index}`}>
                <span className="font-medium text-foreground">
                  {event.event_type.replaceAll(".", " ")}
                </span>
                <span className="block text-text-tertiary">
                  {formatDate(event.timestamp, timezone)} · {event.actor}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-2 text-text-tertiary">No recorded transitions yet.</p>
        )}
      </details>

      {terminal ? (
        <p className="text-sm text-text-tertiary">
          This proposal is terminal and cannot be approved again.
        </p>
      ) : null}
      {error ? (
        <Notice tone="danger" role="alert">
          {error}
        </Notice>
      ) : null}
    </article>
  );
}
