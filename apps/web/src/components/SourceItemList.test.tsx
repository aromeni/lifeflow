import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { SourceItem } from "@/lib/types";

import { SourceItemList } from "./SourceItemList";

const event: SourceItem = {
  id: "1",
  source_type: "calendar_event",
  external_id: "ev-002",
  title: "Northgate workshop — scope & pricing",
  sender_or_organiser: "dana@northgate-consulting.example",
  occurred_at: "2026-07-17T13:00:00+00:00",
  metadata: { location: "Meeting Room 4" },
};

test("renders items with organiser, local time, and location", () => {
  render(<SourceItemList items={[event]} timezone="Europe/London" emptyMessage="Nothing" />);
  expect(screen.getByText("Northgate workshop — scope & pricing")).toBeInTheDocument();
  // 13:00 UTC in July renders as 14:00 in Europe/London (BST).
  expect(screen.getByText(/14:00/)).toBeInTheDocument();
  expect(screen.getByText(/Meeting Room 4/)).toBeInTheDocument();
});

test("shows the empty message when there are no items", () => {
  render(<SourceItemList items={[]} timezone="Europe/London" emptyMessage="No upcoming events." />);
  expect(screen.getByText("No upcoming events.")).toBeInTheDocument();
});
