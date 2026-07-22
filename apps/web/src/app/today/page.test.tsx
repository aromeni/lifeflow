import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { ApiError } from "@/lib/api";
import type { Brief } from "@/lib/types";

import TodayPage from "./page";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: apiMock };
});

const me = {
  id: "u1",
  email: "demo@lifeflow.local",
  display_name: "Demo",
  timezone: "Europe/London",
};

const brief: Brief = {
  id: "b1",
  briefing_date: "2026-07-16T00:00:00+00:00",
  generated_at: "2026-07-16T08:00:00+00:00",
  version: 2,
  status: "complete",
  summary:
    "1 item needs attention; 1 is today or upcoming. 0 follow-ups are waiting; 0 more items have suggested next steps.",
  sections: [
    {
      key: "needs_attention",
      label: "Needs attention",
      items: [
        {
          signal_id: "sig-1",
          signal_type: "request",
          title: "Send the revised proposal to Dana",
          summary: "Dana asked for the revised proposal by Thursday.",
          due_at: null,
          confidence: 0.85,
          priority_score: 0.73,
          priority_band: "high",
          reason_codes: ["explicit_request"],
          actionable: true,
          suggested_action: "Review the request and decide how to respond.",
          evidence: [
            {
              source_item_id: null,
              source_ref: "em-001",
              source_type: "email",
              title: "Re: proposal",
              sender_or_organiser: "dana@northgate-consulting.example",
              occurred_at: "2026-07-14T09:00:00+00:00",
              excerpt: "Could you send it by Thursday?",
            },
          ],
        },
      ],
    },
    { key: "today_upcoming", label: "Today and upcoming", items: [] },
    { key: "waiting_for", label: "Waiting for", items: [] },
    { key: "suggested_actions", label: "Suggested actions", items: [] },
    { key: "low_confidence_review", label: "Low-confidence review", items: [] },
  ],
  notices: [],
  source_window: "past-14d/future-30d",
  prompt_version: null,
  generation_metadata: { llm_summary_used: false },
};

beforeEach(() => {
  apiMock.mockReset();
});

test("renders the latest brief with sections, version, and summary", async () => {
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/me") return me;
    if (path === "/briefs/latest") return brief;
    throw new Error(`unexpected ${path}`);
  });
  render(<TodayPage />);
  expect(await screen.findByText(/1 item needs attention/)).toBeInTheDocument();
  expect(screen.getByText(/version 2/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Needs attention/ })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: /Low-confidence review/ })).toBeInTheDocument();
});

test("offers first-time generation when no brief exists yet", async () => {
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/me") return me;
    if (path === "/briefs/latest") throw new ApiError(404, "not_found", "No brief yet");
    throw new Error(`unexpected ${path}`);
  });
  render(<TodayPage />);
  expect(await screen.findByText("No brief yet.")).toBeInTheDocument();

  apiMock.mockImplementation(async (path: string) => {
    if (path === "/briefs/generate") return brief;
    return me;
  });
  await userEvent.setup().click(screen.getByRole("button", { name: "Generate brief" }));
  expect(await screen.findByText(/1 item needs attention/)).toBeInTheDocument();
});

test("issues one generation request and disables the control while it is in flight", async () => {
  let resolveGeneration: (value: Brief) => void = () => undefined;
  const pendingGeneration = new Promise<Brief>((resolve) => {
    resolveGeneration = resolve;
  });
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/me") return me;
    if (path === "/briefs/latest") return brief;
    if (path === "/briefs/generate") return pendingGeneration;
    throw new Error(`unexpected ${path}`);
  });

  render(<TodayPage />);
  expect(await screen.findByText(/version 2/)).toBeInTheDocument();
  const button = screen.getByRole("button", { name: "Generate brief" });
  const user = userEvent.setup();

  await user.click(button);
  expect(button).toBeDisabled();
  await user.click(button);
  expect(apiMock.mock.calls.filter(([path]) => path === "/briefs/generate")).toHaveLength(1);

  resolveGeneration({ ...brief, id: "b2", version: 3 });
  expect(await screen.findByText(/version 3/)).toBeInTheDocument();
  expect(button).toBeEnabled();
});

test("shows the honest degraded note when model assistance was unavailable", async () => {
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/me") return me;
    if (path === "/briefs/latest")
      return {
        ...brief,
        status: "degraded",
        notices: [
          {
            code: "llm_degraded",
            message:
              "Optional model augmentation was unavailable or rejected. This brief was composed from deterministic signals and rules.",
          },
        ],
      };
    throw new Error(`unexpected ${path}`);
  });
  render(<TodayPage />);
  expect(await screen.findByText(/Optional model assistance was unavailable/)).toBeInTheDocument();
  expect(screen.getByText(/composed from deterministic signals and rules/)).toBeInTheDocument();
});

test("redirects the signed-out visitor to the demo entry point", async () => {
  apiMock.mockImplementation(async () => {
    throw new ApiError(401, "unauthenticated", "Not signed in");
  });
  render(<TodayPage />);
  expect(await screen.findByText(/You are not signed in/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Start the demo" })).toBeInTheDocument();
});
