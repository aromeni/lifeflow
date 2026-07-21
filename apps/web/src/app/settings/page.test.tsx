import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import type { EvidenceFreshness, ScheduledBriefStatus } from "@/lib/types";

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

beforeEach(() => {
  apiMock.mockReset();
});

function mockLoad(
  status: ScheduledBriefStatus = STATUS_DISABLED,
  freshness: EvidenceFreshness = EVIDENCE_EMPTY,
) {
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/me") return ME;
    if (path === "/preferences") return PREFERENCES;
    if (path === "/scheduled-briefs/status") return status;
    if (path === "/evidence-freshness") return freshness;
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
