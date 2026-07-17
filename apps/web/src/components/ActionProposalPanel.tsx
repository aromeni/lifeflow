"use client";

import { useMemo, useState } from "react";

import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { api, ApiError } from "@/lib/api";
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
      className="flex flex-col gap-3 rounded-md border border-current/30 p-4"
    >
      <div>
        <h3 className="font-semibold">Exact approval preview</h3>
        <p className="text-sm opacity-70">
          {ACTION_LABELS[actionType]} · proposal version {version}
        </p>
      </div>
      <dl className="grid gap-2 text-sm sm:grid-cols-[10rem_1fr]">
        {Object.entries(payload).map(([name, value]) => (
          <div key={name} className="contents">
            <dt className="font-medium">{formatFieldName(name)}</dt>
            <dd className="whitespace-pre-wrap break-words">{formatValue(value, timezone)}</dd>
          </div>
        ))}
      </dl>
      <details className="text-xs">
        <summary className="cursor-pointer underline">Exact canonical JSON and hash</summary>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all rounded bg-black/5 p-3 dark:bg-white/10">
          {JSON.stringify({ action_type: actionType, proposal_version: version, payload }, null, 2)}
        </pre>
        <p className="mt-2 break-all font-mono">Payload SHA-256: {payloadHash}</p>
      </details>
    </section>
  );
}

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
  const canApprove = ["proposed", "edited"].includes(proposal.status);
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
      setError(caught instanceof ApiError ? caught.message : "The proposal could not be updated.");
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
      setError(caught instanceof ApiError ? caught.message : "The proposal could not be edited.");
    } finally {
      setPending(null);
    }
  }

  return (
    <article
      data-testid={`proposal-${proposal.action_type}`}
      className="flex flex-col gap-5 rounded-lg border border-current/25 p-5"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2 className="text-xl font-semibold">{ACTION_LABELS[proposal.action_type]}</h2>
          <p>{proposal.rationale}</p>
        </div>
        <span
          data-testid={`proposal-status-${proposal.action_type}`}
          className="rounded-full border border-current/30 px-2.5 py-1 text-xs font-medium uppercase tracking-wide"
        >
          {proposal.status}
        </span>
      </header>

      <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm opacity-75">
        <span>Risk: {proposal.risk_level}</span>
        <span>Confidence: {Math.round(proposal.confidence * 100)}%</span>
        <span>Expires: {formatDate(proposal.expires_at, timezone)}</span>
        <span>Simulation only</span>
      </div>

      <EvidenceDrawer evidence={proposal.evidence} timezone={timezone} />

      <ExactPayloadPreview
        actionType={proposal.action_type}
        version={proposal.version}
        payload={proposal.payload}
        payloadHash={proposal.payload_hash}
        timezone={timezone}
        testId={`payload-preview-${proposal.action_type}`}
      />

      {proposal.approval ? (
        <section
          data-testid="approval-binding"
          className="rounded-md border border-green-700/40 p-3 text-sm"
        >
          <p className="font-medium">Approved exact payload</p>
          <p>
            Version {proposal.approval.proposal_version} · approved{" "}
            {formatDate(proposal.approval.approved_at, timezone)}
          </p>
          <p className="mt-1 break-all font-mono text-xs">
            Binding SHA-256: {proposal.approval.binding_hash}
          </p>
        </section>
      ) : null}

      {editing ? (
        <section className="flex flex-col gap-2">
          <label htmlFor={`payload-${proposal.id}`} className="font-medium">
            Edit every executor input field
          </label>
          <p className="text-sm opacity-70">
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
            className="w-full rounded-md border border-current/30 bg-transparent p-3 font-mono text-sm"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={saveEdit}
              disabled={pending !== null}
              className="rounded bg-foreground px-3 py-2 text-sm text-background disabled:opacity-50"
            >
              {pending === "edit" ? "Saving…" : "Save and invalidate approval"}
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(exactJson);
                setEditing(false);
                setError("");
              }}
              disabled={pending !== null}
              className="rounded border border-current/30 px-3 py-2 text-sm disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </section>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {canApprove ? (
          <button
            type="button"
            data-testid={`approve-${proposal.action_type}`}
            onClick={() =>
              transition("approve", `/action-proposals/${proposal.id}/approve`, {
                expected_version: proposal.version,
                action_type: proposal.action_type,
                displayed_payload_hash: proposal.payload_hash,
              })
            }
            disabled={pending !== null}
            className="rounded bg-foreground px-4 py-2 text-sm font-medium text-background disabled:opacity-50"
          >
            {pending === "approve" ? "Approving…" : "Approve exact payload"}
          </button>
        ) : null}
        {proposal.status === "approved" ? (
          <button
            type="button"
            data-testid={`execute-${proposal.action_type}`}
            onClick={() => transition("execute", `/action-proposals/${proposal.id}/execute`)}
            disabled={pending !== null}
            className="rounded bg-foreground px-4 py-2 text-sm font-medium text-background disabled:opacity-50"
          >
            {pending === "execute" ? "Simulating…" : "Run approved simulation"}
          </button>
        ) : null}
        {canEdit && !editing ? (
          <button
            type="button"
            onClick={() => setEditing(true)}
            disabled={pending !== null}
            className="rounded border border-current/30 px-4 py-2 text-sm disabled:opacity-50"
          >
            Edit exact payload
          </button>
        ) : null}
        {canReject ? (
          <button
            type="button"
            data-testid={`reject-${proposal.action_type}`}
            onClick={() =>
              transition("reject", `/action-proposals/${proposal.id}/reject`, {
                expected_version: proposal.version,
                reason: null,
              })
            }
            disabled={pending !== null}
            className="rounded border border-current/30 px-4 py-2 text-sm disabled:opacity-50"
          >
            {pending === "reject" ? "Rejecting…" : "Reject"}
          </button>
        ) : null}
      </div>

      {proposal.execution ? (
        <section
          data-testid="execution-result"
          className="rounded-md border border-current/30 p-3 text-sm"
        >
          <h3 className="font-medium">Simulation result</h3>
          <p>
            {proposal.execution.outcome} · one execution record · version{" "}
            {proposal.execution.proposal_version}
          </p>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(proposal.execution.result, null, 2)}
          </pre>
        </section>
      ) : null}

      <details data-testid={`audit-trail-${proposal.action_type}`} className="text-sm">
        <summary className="cursor-pointer underline">
          Audit trail ({proposal.audit_events.length} event
          {proposal.audit_events.length === 1 ? "" : "s"})
        </summary>
        {proposal.audit_events.length ? (
          <ol className="mt-2 flex flex-col gap-2 border-l-2 border-current/20 pl-3">
            {proposal.audit_events.map((event, index) => (
              <li key={`${event.timestamp}-${event.event_type}-${index}`}>
                <span className="font-medium">{event.event_type.replaceAll(".", " ")}</span>
                <span className="block opacity-70">
                  {formatDate(event.timestamp, timezone)} · {event.actor}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="mt-2 opacity-70">No recorded transitions yet.</p>
        )}
      </details>

      {terminal ? (
        <p className="text-sm opacity-70">
          This proposal is terminal and cannot be approved again.
        </p>
      ) : null}
      <p role="alert" aria-live="polite" className="text-sm text-red-700 dark:text-red-400">
        {error}
      </p>
    </article>
  );
}
