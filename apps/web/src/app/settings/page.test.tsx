import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import type { EvidenceFreshness, MemoryItem, MemoryList, ScheduledBriefStatus } from "@/lib/types";

import SettingsPage from "./page";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: apiMock };
});

const ME = { timezone: "Europe/London" };
const PREFERENCES = {
  preferences: [
    {
      key: "briefing_time",
      value: { value: "06:45" },
      provenance: "explicit",
      is_default: false,
      updated_at: "2026-07-21T10:00:00Z",
    },
    {
      key: "working_hours",
      value: { start: "09:00", end: "17:30" },
      provenance: "explicit",
      is_default: true,
      updated_at: null,
    },
    {
      key: "brief_sections",
      value: { sections: ["today_upcoming", "waiting_for"] },
      provenance: "explicit",
      is_default: false,
      updated_at: "2026-07-21T10:00:00Z",
    },
    {
      key: "scheduled_briefs_enabled",
      value: { enabled: false },
      provenance: "explicit",
      is_default: true,
      updated_at: null,
    },
  ],
};

const STATUS_DISABLED: ScheduledBriefStatus = {
  enabled: false,
  timezone: "Europe/London",
  briefing_time: "06:45",
  next_run_at: null,
  latest_run_status: null,
  latest_run_local_date: null,
  latest_run_completed_at: null,
  latest_run_error_code: null,
  latest_brief_id: null,
  latest_brief_version: null,
  scheduler_available: true,
};

const STATUS_ENABLED: ScheduledBriefStatus = {
  ...STATUS_DISABLED,
  enabled: true,
  next_run_at: "2026-07-22T06:45:00Z",
  latest_run_status: "succeeded",
  latest_run_local_date: "2026-07-21",
  latest_run_completed_at: "2026-07-21T06:45:03Z",
  latest_brief_id: "b-sched-1",
  latest_brief_version: 4,
};

const EVIDENCE_EMPTY: EvidenceFreshness = {
  accounts: [],
  scheduled_briefs_use_latest_synced_evidence: true,
};

const EVIDENCE_GOOGLE_SYNCED: EvidenceFreshness = {
  accounts: [
    {
      provider: "google",
      connected: true,
      sync_state: "synced",
      last_synced_at: "2026-07-21T05:00:00Z",
      freshness_band: "fresh",
    },
  ],
  scheduled_briefs_use_latest_synced_evidence: true,
};

const MEMORY_CANDIDATE: MemoryItem = {
  id: "mem-1",
  memory_key: "preferred_email_signoff",
  value: { value: "Kind regards" },
  status: "candidate",
  confidence: 0.72,
  confidence_band: "high",
  evidence_count: 3,
  first_observed_at: "2026-07-18T09:00:00Z",
  last_observed_at: "2026-07-21T09:00:00Z",
  last_evaluated_at: "2026-07-21T09:00:00Z",
  expires_at: null,
  application_mode: "suggest_only",
  corresponding_preference_key: "preferred_email_signoff",
  applied: false,
  overridden_by_explicit: false,
  explanation:
    'You ended 3 draft replies with "Kind regards" after editing them, so LifeFlow suggests using it as your sign-off.',
  version: 1,
  updated_at: "2026-07-21T09:00:00Z",
  evidence: [],
};

const MEMORY_EMPTY: MemoryList = { memories: [], count: 0, inference_enabled: false };
const MEMORY_WITH_CANDIDATE: MemoryList = {
  memories: [MEMORY_CANDIDATE],
  count: 1,
  inference_enabled: true,
};

beforeEach(() => {
  apiMock.mockReset();
});

function mockLoad(
  status: ScheduledBriefStatus = STATUS_DISABLED,
  freshness: EvidenceFreshness = EVIDENCE_EMPTY,
  memory: MemoryList = MEMORY_EMPTY,
) {
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/me") return ME;
    if (path === "/preferences") return PREFERENCES;
    if (path === "/scheduled-briefs/status") return status;
    if (path === "/evidence-freshness") return freshness;
    if (path === "/memories") return memory;
    return {};
  });
}

test("settings render stored preferences and disclose the always-shown section", async () => {
  mockLoad();
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId("settings-briefing-time")).toBeInTheDocument());

  expect(screen.getByTestId("settings-timezone")).toHaveValue("Europe/London");
  expect(screen.getByTestId("settings-briefing-time")).toHaveValue("06:45");
  expect(screen.getByTestId("settings-section-today_upcoming")).toBeChecked();
  expect(screen.getByTestId("settings-section-waiting_for")).toBeChecked();
  expect(screen.getByTestId("settings-section-suggested_actions")).not.toBeChecked();
  // D45 disclosure: the user is told needs-attention can never be hidden,
  // and no checkbox exists for it.
  expect(screen.getByText(/always shown/i)).toBeInTheDocument();
  // Truthfulness: briefing time is stored but only becomes operational once
  // scheduled briefs are actually enabled (not merely checked-but-unsaved).
  expect(screen.getByText(/not yet in use/i)).toBeInTheDocument();
  expect(screen.queryByTestId("settings-section-needs_attention")).not.toBeInTheDocument();
  expect(screen.getByTestId("settings-schedule-enabled")).not.toBeChecked();
  expect(screen.queryByTestId("settings-schedule-status")).not.toBeInTheDocument();
});

test("saving writes each preference and confirms in plain language", async () => {
  mockLoad();
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId("settings-save")).toBeInTheDocument());

  await userEvent.click(screen.getByTestId("settings-section-suggested_actions"));
  await userEvent.click(screen.getByTestId("settings-save"));

  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/settings saved/i));
  const putCalls = apiMock.mock.calls.filter(([, init]) => init?.method === "PUT");
  const putPaths = putCalls.map(([path]) => path);
  expect(putPaths).toContain("/preferences/briefing_time");
  expect(putPaths).toContain("/preferences/working_hours");
  expect(putPaths).toContain("/preferences/brief_sections");
  expect(putPaths).toContain("/preferences/scheduled_briefs_enabled");
  const sectionsBody = JSON.parse(
    putCalls.find(([path]) => path === "/preferences/brief_sections")![1].body as string,
  );
  expect(sectionsBody.value.sections).toEqual(
    expect.arrayContaining(["today_upcoming", "waiting_for", "suggested_actions"]),
  );
});

test("enabling scheduled briefs and saving shows the real next/last run status, never approving or executing anything", async () => {
  mockLoad();
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId("settings-schedule-enabled")).toBeInTheDocument());

  await userEvent.click(screen.getByTestId("settings-schedule-enabled"));
  // Saving refetches status; simulate the backend now reporting it enabled.
  apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path === "/me") return ME;
    if (path === "/preferences") return PREFERENCES;
    if (path === "/scheduled-briefs/status") return STATUS_ENABLED;
    if (init?.method === "PUT") return {};
    return {};
  });
  await userEvent.click(screen.getByTestId("settings-save"));

  await waitFor(() => expect(screen.getByTestId("settings-schedule-status")).toBeInTheDocument());
  expect(screen.getByText(/Next scheduled brief/)).toBeInTheDocument();
  expect(screen.getByText(/succeeded/)).toBeInTheDocument();
  expect(screen.getByText(/brief version 4/)).toBeInTheDocument();
  expect(screen.queryByTestId("settings-schedule-unavailable")).not.toBeInTheDocument();
  const putBody = JSON.parse(
    apiMock.mock.calls.find(
      ([path, init]) => path === "/preferences/scheduled_briefs_enabled" && init?.method === "PUT",
    )![1].body as string,
  );
  expect(putBody.value.enabled).toBe(true);
});

test("shows evidence freshness for a connected, synced account", async () => {
  mockLoad(STATUS_DISABLED, EVIDENCE_GOOGLE_SYNCED);
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId("evidence-freshness-google")).toBeInTheDocument());
  expect(screen.getByTestId("evidence-freshness-google")).toHaveTextContent(/last synced/i);
  expect(screen.getByTestId("evidence-freshness-google")).toHaveTextContent(/up to date/i);
});

test("discloses when no evidence source is connected yet", async () => {
  mockLoad(STATUS_DISABLED, EVIDENCE_EMPTY);
  render(<SettingsPage />);
  await waitFor(() =>
    expect(screen.getByTestId("settings-evidence-freshness")).toBeInTheDocument(),
  );
  expect(screen.getByText(/no accounts connected yet/i)).toBeInTheDocument();
});

test("shows a truthful notice when the scheduler is not reachable", async () => {
  mockLoad({ ...STATUS_ENABLED, scheduler_available: false });
  render(<SettingsPage />);
  await waitFor(() =>
    expect(screen.getByTestId("settings-schedule-unavailable")).toBeInTheDocument(),
  );
});

// --- Memory section (Stage 8 Phase 3) --------------------------------------

test("memory section states the truthful learning boundaries and shows the empty state", async () => {
  mockLoad();
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId("settings-memory-enabled")).toBeInTheDocument());
  expect(screen.getByTestId("settings-memory-enabled")).not.toBeChecked();
  expect(screen.getByTestId("settings-memory-empty")).toBeInTheDocument();
  // Required truthfulness copy.
  expect(screen.getByText(/never treated as your preference/i)).toBeInTheDocument();
  expect(screen.getByText(/explicit settings always take priority/i)).toBeInTheDocument();
  expect(screen.getByText(/never approves or sends anything/i)).toBeInTheDocument();
  expect(screen.getByText(/does not delete anything in Gmail or Calendar/i)).toBeInTheDocument();
});

test("a candidate shows its value, confidence, rationale and controls", async () => {
  mockLoad(STATUS_DISABLED, EVIDENCE_EMPTY, MEMORY_WITH_CANDIDATE);
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId("memory-item-mem-1")).toBeInTheDocument());
  expect(screen.getByTestId("memory-value-mem-1")).toHaveTextContent("Kind regards");
  expect(screen.getByTestId("memory-status-mem-1")).toHaveTextContent(
    /not applied until you confirm/i,
  );
  expect(screen.getByTestId("memory-explanation-mem-1")).toHaveTextContent(/after editing them/i);
  expect(screen.getByText(/Confidence: High \(0.72\)/)).toBeInTheDocument();
  // Confirm / edit / dismiss / delete are all present for a candidate.
  expect(screen.getByTestId("memory-confirm-mem-1")).toBeInTheDocument();
  expect(screen.getByTestId("memory-edit-mem-1")).toBeInTheDocument();
  expect(screen.getByTestId("memory-dismiss-mem-1")).toBeInTheDocument();
  expect(screen.getByTestId("memory-delete-mem-1")).toBeInTheDocument();
  // Pause and delete-all are distinct controls.
  expect(screen.getByTestId("settings-memory-enabled")).toBeChecked();
  expect(screen.getByTestId("settings-memory-delete-all")).toBeInTheDocument();
});

test("confirming a candidate calls the confirm endpoint and reports success", async () => {
  mockLoad(STATUS_DISABLED, EVIDENCE_EMPTY, MEMORY_WITH_CANDIDATE);
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId("memory-confirm-mem-1")).toBeInTheDocument());
  await userEvent.click(screen.getByTestId("memory-confirm-mem-1"));
  await waitFor(() =>
    expect(screen.getByTestId("settings-memory-message")).toHaveTextContent(
      /future draft replies/i,
    ),
  );
  const confirmCall = apiMock.mock.calls.find(
    ([path, init]) => path === "/memories/mem-1/confirm" && init?.method === "POST",
  );
  expect(confirmCall).toBeDefined();
  expect(JSON.parse(confirmCall![1].body as string)).toEqual({ expected_version: 1 });
});

test("edit-and-confirm sends the edited value", async () => {
  mockLoad(STATUS_DISABLED, EVIDENCE_EMPTY, MEMORY_WITH_CANDIDATE);
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId("memory-edit-mem-1")).toBeInTheDocument());
  await userEvent.click(screen.getByTestId("memory-edit-mem-1"));
  const input = screen.getByTestId("memory-edit-input-mem-1");
  await userEvent.clear(input);
  await userEvent.type(input, "Warm regards");
  await userEvent.click(screen.getByTestId("memory-save-mem-1"));
  await waitFor(() => {
    const putCall = apiMock.mock.calls.find(
      ([path, init]) => path === "/memories/mem-1" && init?.method === "PUT",
    );
    expect(putCall).toBeDefined();
    expect(JSON.parse(putCall![1].body as string)).toEqual({
      expected_version: 1,
      value: "Warm regards",
    });
  });
});

test("dismiss and delete-all call distinct endpoints", async () => {
  mockLoad(STATUS_DISABLED, EVIDENCE_EMPTY, MEMORY_WITH_CANDIDATE);
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId("memory-dismiss-mem-1")).toBeInTheDocument());
  await userEvent.click(screen.getByTestId("memory-dismiss-mem-1"));
  await waitFor(() =>
    expect(
      apiMock.mock.calls.some(
        ([path, init]) => path === "/memories/mem-1/dismiss" && init?.method === "POST",
      ),
    ).toBe(true),
  );
  await userEvent.click(screen.getByTestId("settings-memory-delete-all"));
  await waitFor(() =>
    expect(
      apiMock.mock.calls.some(([path, init]) => path === "/memories" && init?.method === "DELETE"),
    ).toBe(true),
  );
});

test("pausing inference writes the preference off without deleting memory", async () => {
  mockLoad(STATUS_DISABLED, EVIDENCE_EMPTY, MEMORY_WITH_CANDIDATE);
  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByTestId("settings-memory-enabled")).toBeChecked());
  await userEvent.click(screen.getByTestId("settings-memory-enabled"));
  await waitFor(() =>
    expect(screen.getByTestId("settings-memory-message")).toHaveTextContent(/learning paused/i),
  );
  const putCall = apiMock.mock.calls.find(
    ([path, init]) => path === "/preferences/memory_inference_enabled" && init?.method === "PUT",
  );
  expect(putCall).toBeDefined();
  expect(JSON.parse(putCall![1].body as string)).toEqual({ value: { enabled: false } });
  // No DELETE was issued — pausing never deletes.
  expect(apiMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(false);
});
