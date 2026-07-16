import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import type { BriefItem, BriefSection } from "@/lib/types";

import { BriefSectionView } from "./BriefSectionView";

const item: BriefItem = {
  signal_id: "sig-1",
  signal_type: "request",
  title: "Send the revised proposal to Dana",
  summary: "Dana asked for the revised proposal by Thursday.",
  due_at: "2026-07-16T22:59:00+00:00",
  confidence: 0.85,
  priority_score: 0.73,
  priority_band: "high",
  reason_codes: ["explicit_request", "due_within_24h", "no_reply_6d"],
  actionable: true,
  suggested_action: "Review the request and decide how to respond.",
  evidence: [
    {
      source_item_id: "11111111-1111-1111-1111-111111111111",
      source_ref: "em-001",
      source_type: "email",
      title: "Re: proposal",
      sender_or_organiser: "dana@northgate-consulting.example",
      occurred_at: "2026-07-14T09:00:00+00:00",
      excerpt: "Could you send the revised proposal by Thursday?",
    },
  ],
};

const section: BriefSection = {
  key: "needs_attention",
  label: "Needs attention",
  items: [item],
};

test("renders the item with band, readable reasons, and suggested action", () => {
  render(<BriefSectionView section={section} timezone="Europe/London" />);
  expect(screen.getByRole("heading", { name: /Needs attention/ })).toBeInTheDocument();
  expect(screen.getByText("Send the revised proposal to Dana")).toBeInTheDocument();
  expect(screen.getByText(/high priority/i)).toBeInTheDocument();
  expect(screen.getByText("Explicit request from sender")).toBeInTheDocument();
  expect(screen.getByText("No reply for 6 days")).toBeInTheDocument();
  expect(screen.getByText(/Review the request and decide how to respond/)).toBeInTheDocument();
  expect(screen.getByText(/nothing happens without your approval/)).toBeInTheDocument();
});

test("evidence drawer discloses the source with reference and excerpt", async () => {
  const user = userEvent.setup();
  render(<BriefSectionView section={section} timezone="Europe/London" />);
  await user.click(screen.getByText(/Evidence \(1 source\)/));
  expect(screen.getByText("Re: proposal")).toBeInTheDocument();
  expect(screen.getByText(/ref em-001/)).toBeInTheDocument();
  expect(screen.getByText(/Could you send the revised proposal by Thursday\?/)).toBeInTheDocument();
});

test("shows an honest empty message for a section with no items", () => {
  render(
    <BriefSectionView
      section={{ key: "waiting_for", label: "Waiting for", items: [] }}
      timezone="Europe/London"
    />,
  );
  expect(screen.getByText("Nothing here right now.")).toBeInTheDocument();
});
