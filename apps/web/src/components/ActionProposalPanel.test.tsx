import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import type { ActionProposal } from "@/lib/types";

import { ActionProposalPanel } from "./ActionProposalPanel";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: apiMock };
});

const proposal: ActionProposal = {
  id: "proposal-1",
  origin_fingerprint: "a".repeat(64),
  action_type: "create_gmail_draft",
  rationale: "Prepare an evidence-backed draft; this never sends email.",
  source_refs: ["em-001"],
  evidence: [
    {
      source_item_id: "source-1",
      source_ref: "em-001",
      source_type: "email",
      title: "Quarterly review",
      sender_or_organiser: "dana@northgate-consulting.example",
      occurred_at: "2026-07-15T08:00:00Z",
      excerpt: "Could you confirm the revised figures?",
    },
  ],
  payload: {
    to: ["dana@northgate-consulting.example"],
    subject: "Re: Quarterly review",
    body: "Hi Dana,\n\nI am reviewing it and will follow up.\n\nBest",
    thread_id: "thread-001",
  },
  payload_hash: "b".repeat(64),
  version: 1,
  risk_level: "medium",
  confidence: 0.9,
  status: "proposed",
  expires_at: "2026-07-20T08:00:00Z",
  approval: null,
  execution: null,
  rejection_reason: null,
  created_at: "2026-07-16T08:00:00Z",
  updated_at: "2026-07-16T08:00:00Z",
  audit_events: [],
  execution_mode: "simulation",
  simulation_only: true,
  execution_context: { mode: "simulation", provider: "synthetic", required_scope: null },
  execution_context_hash: "e".repeat(64),
  approved_execution_context: null,
  execution_context_changed: false,
};

beforeEach(() => {
  apiMock.mockReset();
});

test("shows evidence and every exact executor field before approval", () => {
  render(<ActionProposalPanel proposal={proposal} timezone="Europe/London" onChanged={vi.fn()} />);

  expect(screen.getByText("Evidence (1 source)")).toBeInTheDocument();
  expect(screen.getByText("dana@northgate-consulting.example")).toBeInTheDocument();
  expect(screen.getByText("Re: Quarterly review")).toBeInTheDocument();
  expect(screen.getByText("thread-001")).toBeInTheDocument();
  expect(screen.getAllByText(/I am reviewing it and will follow up/)).toHaveLength(2);
  expect(screen.getByText(/proposal version 1/)).toBeInTheDocument();
  expect(screen.getByTestId("execution-mode-notice")).toHaveTextContent(
    "This action will be simulated",
  );
});

test("a real Google-connected gmail-draft proposal discloses the real action before approval", () => {
  const realProposal: ActionProposal = {
    ...proposal,
    execution_mode: "real",
    simulation_only: false,
  };
  render(
    <ActionProposalPanel proposal={realProposal} timezone="Europe/London" onChanged={vi.fn()} />,
  );

  expect(screen.getByTestId("execution-mode-notice")).toHaveTextContent(
    "This will create a real draft in your connected Gmail account. It will not send the email.",
  );
});

test("a real Google-connected calendar-event proposal discloses the real action before approval", () => {
  const realCalendarProposal: ActionProposal = {
    ...proposal,
    action_type: "create_calendar_event",
    execution_mode: "real",
    simulation_only: false,
    payload: {
      title: "Project sync",
      starts_at: "2026-07-20T10:00:00Z",
      ends_at: "2026-07-20T10:30:00Z",
      timezone: "Europe/London",
      location: null,
      description: "",
      attendees: ["dana@northgate-consulting.example"],
    },
  };
  render(
    <ActionProposalPanel
      proposal={realCalendarProposal}
      timezone="Europe/London"
      onChanged={vi.fn()}
    />,
  );

  expect(screen.getByTestId("execution-mode-notice")).toHaveTextContent(
    "This will create a real event in your connected Google Calendar. Guest notifications are off.",
  );
});

test("a proposal with no capable connected account discloses that execution is unavailable", () => {
  const unavailableProposal: ActionProposal = {
    ...proposal,
    execution_mode: "unavailable",
    simulation_only: true,
  };
  render(
    <ActionProposalPanel
      proposal={unavailableProposal}
      timezone="Europe/London"
      onChanged={vi.fn()}
    />,
  );

  expect(screen.getByTestId("execution-mode-notice")).toHaveTextContent(
    "Unavailable — cannot approve or execute",
  );
});

test("calendar-event proposals disclose that guest notifications are off", () => {
  const calendarProposal: ActionProposal = {
    ...proposal,
    action_type: "create_calendar_event",
    payload: {
      title: "Project sync",
      starts_at: "2026-07-20T10:00:00Z",
      ends_at: "2026-07-20T10:30:00Z",
      timezone: "Europe/London",
      location: null,
      description: "",
      attendees: ["dana@northgate-consulting.example"],
    },
  };
  render(
    <ActionProposalPanel
      proposal={calendarProposal}
      timezone="Europe/London"
      onChanged={vi.fn()}
    />,
  );

  expect(screen.getByTestId("guest-notifications-notice")).toHaveTextContent(
    "Guest notifications: off",
  );
});

test("a gmail-draft proposal shows no guest-notifications notice", () => {
  render(<ActionProposalPanel proposal={proposal} timezone="Europe/London" onChanged={vi.fn()} />);

  expect(screen.queryByTestId("guest-notifications-notice")).not.toBeInTheDocument();
});

test("an uncertain execution shows the no-automatic-retry warning", () => {
  const uncertainProposal: ActionProposal = {
    ...proposal,
    status: "executing",
    execution: {
      id: "execution-1",
      idempotency_key: "e".repeat(40),
      outcome: "uncertain",
      effective_status: "uncertain",
      execution_mode: "real",
      simulation_only: false,
      started_at: "2026-07-16T09:00:00Z",
      completed_at: null,
      action_type: proposal.action_type,
      proposal_version: proposal.version,
      executed_payload: proposal.payload,
      executed_payload_hash: proposal.payload_hash,
      approval_binding_hash: "c".repeat(64),
      result: { message: "Gmail did not confirm draft creation before the call ended." },
      error_code: null,
    },
  };
  render(
    <ActionProposalPanel
      proposal={uncertainProposal}
      timezone="Europe/London"
      onChanged={vi.fn()}
    />,
  );

  expect(screen.getByTestId("execution-uncertain-warning")).toHaveTextContent(
    "has not been retried automatically",
  );
  expect(screen.getByTestId("execution-result")).toHaveTextContent(
    "Outcome uncertain — not retried automatically",
  );
  // The dominant top-of-card label must say the outcome is uncertain, not
  // just repeat the internal "executing" in-flight status (a real sandbox
  // execution surfaced this as confusing — the draft had actually been
  // created, but the badge read as "still running").
  expect(screen.getByTestId(`proposal-status-${proposal.action_type}`)).toHaveTextContent(
    "Execution outcome uncertain",
  );
});

test("an approval-context-changed failure is disclosed as not attempted, never retried", () => {
  const blockedProposal: ActionProposal = {
    ...proposal,
    status: "failed",
    execution: {
      id: "execution-3",
      idempotency_key: "d".repeat(40),
      outcome: "failed",
      effective_status: "failed",
      execution_mode: "real",
      simulation_only: false,
      started_at: "2026-07-16T09:00:00Z",
      completed_at: "2026-07-16T09:00:01Z",
      action_type: proposal.action_type,
      proposal_version: proposal.version,
      executed_payload: proposal.payload,
      executed_payload_hash: proposal.payload_hash,
      approval_binding_hash: "c".repeat(64),
      result: {
        status: "failed",
        message:
          "The approved account, authorisation, or scope changed before execution. No external action was attempted.",
      },
      error_code: "approval_context_changed",
    },
  };
  render(
    <ActionProposalPanel proposal={blockedProposal} timezone="Europe/London" onChanged={vi.fn()} />,
  );

  expect(screen.getByTestId("execution-result")).toHaveTextContent(
    "Not executed — approval context changed",
  );
  expect(screen.getByTestId("approval-context-changed-warning")).toHaveTextContent(
    "no external action was attempted",
  );
  expect(screen.queryByText("Execution failed")).not.toBeInTheDocument();
});

test("the approve button is disabled and absent for an unavailable proposal", () => {
  const unavailableProposal: ActionProposal = {
    ...proposal,
    execution_mode: "unavailable",
    simulation_only: true,
  };
  render(
    <ActionProposalPanel
      proposal={unavailableProposal}
      timezone="Europe/London"
      onChanged={vi.fn()}
    />,
  );

  expect(
    screen.queryByTestId(`approve-${unavailableProposal.action_type}`),
  ).not.toBeInTheDocument();
});

test("a real gmail execution result is labelled as a real draft, not a simulation", () => {
  const realExecuted: ActionProposal = {
    ...proposal,
    status: "executed",
    execution_mode: "real",
    simulation_only: false,
    execution: {
      id: "execution-2",
      idempotency_key: "f".repeat(40),
      outcome: "succeeded",
      effective_status: "succeeded",
      execution_mode: "real",
      simulation_only: false,
      started_at: "2026-07-16T09:00:00Z",
      completed_at: "2026-07-16T09:00:01Z",
      action_type: proposal.action_type,
      proposal_version: proposal.version,
      executed_payload: proposal.payload,
      executed_payload_hash: proposal.payload_hash,
      approval_binding_hash: "c".repeat(64),
      result: { status: "created", draft_id: "draft-1", message: "Gmail draft created." },
      error_code: null,
    },
  };
  render(
    <ActionProposalPanel proposal={realExecuted} timezone="Europe/London" onChanged={vi.fn()} />,
  );

  expect(screen.getByTestId("execution-result")).toHaveTextContent("Gmail draft created");
  expect(screen.queryByText("Simulation result")).not.toBeInTheDocument();
});

test("a changed execution context shows a banner and disables execute", () => {
  const staleApproved: ActionProposal = {
    ...proposal,
    status: "approved",
    execution_context_changed: true,
    approval: {
      action_type: proposal.action_type,
      proposal_version: proposal.version,
      payload: proposal.payload,
      payload_hash: proposal.payload_hash,
      binding_hash: "c".repeat(64),
      approved_at: "2026-07-16T09:00:00Z",
      execution_context: { mode: "simulation", provider: "synthetic", required_scope: null },
    },
  };
  render(
    <ActionProposalPanel proposal={staleApproved} timezone="Europe/London" onChanged={vi.fn()} />,
  );

  expect(screen.getByTestId("execution-context-changed-notice")).toHaveTextContent(
    "Execution context changed since approval",
  );
  expect(screen.getByTestId(`execute-${proposal.action_type}`)).toBeDisabled();
});

test("approval request binds the displayed type, hash, and version", async () => {
  const approved: ActionProposal = {
    ...proposal,
    status: "approved",
    approval: {
      action_type: proposal.action_type,
      proposal_version: proposal.version,
      payload: proposal.payload,
      payload_hash: proposal.payload_hash,
      binding_hash: "c".repeat(64),
      approved_at: "2026-07-16T09:00:00Z",
      execution_context: { mode: "simulation", provider: "synthetic", required_scope: null },
    },
  };
  apiMock.mockResolvedValue(approved);
  const onChanged = vi.fn();
  render(
    <ActionProposalPanel proposal={proposal} timezone="Europe/London" onChanged={onChanged} />,
  );

  await userEvent.setup().click(screen.getByRole("button", { name: "Approve exact payload" }));

  expect(apiMock).toHaveBeenCalledTimes(1);
  const [path, init] = apiMock.mock.calls[0];
  expect(path).toBe("/action-proposals/proposal-1/approve");
  expect(JSON.parse(init.body)).toEqual({
    expected_version: 1,
    action_type: "create_gmail_draft",
    displayed_payload_hash: "b".repeat(64),
    displayed_execution_context_hash: "e".repeat(64),
  });
  expect(onChanged).toHaveBeenCalledWith(approved);
});

test("editing an approved preview sends the current version and removes approval", async () => {
  const approved: ActionProposal = {
    ...proposal,
    status: "approved",
    approval: {
      action_type: proposal.action_type,
      proposal_version: proposal.version,
      payload: proposal.payload,
      payload_hash: proposal.payload_hash,
      binding_hash: "c".repeat(64),
      approved_at: "2026-07-16T09:00:00Z",
      execution_context: { mode: "simulation", provider: "synthetic", required_scope: null },
    },
  };
  const editedPayload = { ...proposal.payload, subject: "Re: Revised quarterly review" };
  const edited: ActionProposal = {
    ...proposal,
    payload: editedPayload,
    payload_hash: "d".repeat(64),
    version: 2,
    status: "edited",
    approval: null,
  };
  apiMock.mockResolvedValue(edited);
  const onChanged = vi.fn();
  const { rerender } = render(
    <ActionProposalPanel
      proposal={approved}
      timezone="Europe/London"
      onChanged={(changed) => {
        onChanged(changed);
        rerender(
          <ActionProposalPanel proposal={changed} timezone="Europe/London" onChanged={onChanged} />,
        );
      }}
    />,
  );

  expect(screen.getByText("Approved exact payload")).toBeInTheDocument();
  await userEvent.setup().click(screen.getByRole("button", { name: "Edit exact payload" }));
  fireEvent.change(screen.getByTestId("payload-editor-create_gmail_draft"), {
    target: { value: JSON.stringify(editedPayload, null, 2) },
  });
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "Save and invalidate approval" }));

  const [path, init] = apiMock.mock.calls[0];
  expect(path).toBe("/action-proposals/proposal-1");
  expect(JSON.parse(init.body)).toEqual({
    expected_version: 1,
    action_type: "create_gmail_draft",
    payload: editedPayload,
  });
  await waitFor(() => expect(screen.queryByText("Approved exact payload")).not.toBeInTheDocument());
  expect(screen.getByText(/proposal version 2/)).toBeInTheDocument();
});
