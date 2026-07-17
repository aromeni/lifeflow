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
  simulation_only: true,
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
  expect(screen.getByText(/Simulation only/)).toBeInTheDocument();
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
