import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import type { ConnectionSummary, GoogleSyncResult, PrivacySummary } from "@/lib/types";

import ConnectionsPage from "./page";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: apiMock };
});

const GMAIL_RO = "https://www.googleapis.com/auth/gmail.readonly";
const GMAIL_COMPOSE = "https://www.googleapis.com/auth/gmail.compose";

function googleConnection(overrides: Partial<ConnectionSummary> = {}): ConnectionSummary {
  return {
    account_id: "acc-1",
    provider: "google",
    status: "active",
    connected: true,
    granted_scopes: [
      { scope: GMAIL_RO, label: "View Gmail evidence" },
      { scope: GMAIL_COMPOSE, label: "Create Gmail drafts" },
    ],
    last_synced_at: "2026-07-21T06:00:00Z",
    freshness_band: "aging",
    ever_synced: true,
    can_disconnect: true,
    can_reconnect: true,
    ...overrides,
  };
}

function summaryWith(connections: ConnectionSummary[]): PrivacySummary {
  return {
    connections,
    inventory: {
      connected_accounts: connections.length,
      source_items: 42,
      signals: 7,
      briefs: 3,
      brief_versions: 5,
      action_proposals: 4,
      action_executions: 2,
      scheduled_brief_runs: 1,
      preferences: 3,
      memory_items: 1,
      memory_evidence: 2,
      audit_events: 11,
    },
    retention: {
      enforcement_active: false,
      classes: [
        {
          key: "source_items",
          label: "Imported emails & events",
          description: "…",
          retention_days: 30,
          enforced: false,
        },
        {
          key: "pending_uncertain_executions",
          label: "Unresolved external outcomes",
          description: "…",
          retention_days: null,
          enforced: false,
        },
      ],
      notes: ["Provisional product defaults."],
    },
  };
}

function syncResult(overrides: Partial<GoogleSyncResult>): GoogleSyncResult {
  return {
    imported: 181,
    updated: 0,
    unchanged: 0,
    gmail_excluded: 0,
    gmail_incomplete: 0,
    calendar_incomplete: 0,
    gmail_synced: true,
    gmail_cursor_status: "incremental",
    gmail_sync_complete: true,
    calendar_synced: true,
    calendar_cursor_status: "initial",
    calendar_sync_complete: true,
    ...overrides,
  };
}

/** Route the mocked `api` by path so the page can fetch /privacy/summary and,
 *  independently, POST sync/disconnect — mirroring the real client. */
function mockApi(options: {
  summary: PrivacySummary | (() => PrivacySummary);
  sync?: GoogleSyncResult;
  summaryError?: boolean;
}) {
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/privacy/summary") {
      if (options.summaryError) throw Object.assign(new Error("boom"), { status: 500 });
      return typeof options.summary === "function" ? options.summary() : options.summary;
    }
    if (path === "/connected-accounts/google/sync") return options.sync ?? syncResult({});
    if (path === "/connected-accounts/google/disconnect") return undefined;
    throw new Error(`unexpected path ${path}`);
  });
}

beforeEach(() => {
  apiMock.mockReset();
});

test("renders connected account status, scope labels, freshness and inventory counts", async () => {
  mockApi({ summary: summaryWith([googleConnection()]) });
  render(<ConnectionsPage />);

  // 21 status, 22 labels, 24 freshness, 25 inventory
  await waitFor(() =>
    expect(screen.getByTestId("google-connection-status")).toHaveTextContent("active"),
  );
  expect(screen.getByText("View Gmail evidence")).toBeInTheDocument();
  expect(screen.getByText("Create Gmail drafts")).toBeInTheDocument();
  expect(screen.getByTestId("evidence-freshness")).toHaveTextContent(/Aging/i);
  expect(screen.getByTestId("inventory-source_items")).toHaveTextContent("42");
  expect(screen.getByTestId("inventory-audit_events")).toHaveTextContent("11");
});

test("technical scope detail is collapsible and reveals the exact granted scopes", async () => {
  mockApi({ summary: summaryWith([googleConnection()]) });
  render(<ConnectionsPage />);

  const details = await screen.findByTestId("scope-technical-details");
  expect(details).toBeInstanceOf(HTMLDetailsElement);
  await userEvent.setup().click(screen.getByText("Technical detail"));
  expect(screen.getByText(GMAIL_RO)).toBeInTheDocument();
});

test("never-synced state is shown truthfully", async () => {
  mockApi({
    summary: summaryWith([
      googleConnection({ ever_synced: false, freshness_band: null, last_synced_at: null }),
    ]),
  });
  render(<ConnectionsPage />);
  await waitFor(() =>
    expect(screen.getByTestId("evidence-freshness")).toHaveTextContent(/Never synced/i),
  );
});

test("retention copy makes clear enforcement is not switched on yet", async () => {
  mockApi({ summary: summaryWith([googleConnection()]) });
  render(<ConnectionsPage />);
  await waitFor(() =>
    expect(screen.getByTestId("retention-not-enforced")).toHaveTextContent(
      /not switched on yet/i,
    ),
  );
  expect(screen.getByTestId("retention-not-enforced")).toHaveTextContent(
    /not.*deleted automatically/i,
  );
});

test("the four data controls are distinct and imported-data/account deletion have no active button", async () => {
  mockApi({ summary: summaryWith([googleConnection()]) });
  render(<ConnectionsPage />);

  await screen.findByTestId("data-controls");
  // 28 four distinct controls
  expect(screen.getByTestId("control-disconnect")).toBeInTheDocument();
  expect(screen.getByTestId("control-delete-imported")).toBeInTheDocument();
  expect(screen.getByTestId("control-delete-memory")).toBeInTheDocument();
  expect(screen.getByTestId("control-delete-account")).toBeInTheDocument();
  // 27 disconnect explains imported data remains
  expect(screen.getByTestId("control-disconnect")).toHaveTextContent(/already imported stays/i);
  // 29 no active destructive buttons
  expect(
    screen.getByTestId("control-delete-imported").querySelector("button"),
  ).toBeNull();
  expect(
    screen.getByTestId("control-delete-account").querySelector("button"),
  ).toBeNull();
});

test("preferences and learned-preferences links point at settings", async () => {
  mockApi({ summary: summaryWith([googleConnection()]) });
  render(<ConnectionsPage />);
  await waitFor(() => expect(screen.getByTestId("preferences-link")).toHaveAttribute("href", "/settings"));
  expect(screen.getByTestId("learned-preferences-link")).toHaveAttribute("href", "/settings");
});

test("a load error is announced accessibly", async () => {
  mockApi({ summary: summaryWith([]), summaryError: true });
  render(<ConnectionsPage />);
  await waitFor(() =>
    expect(screen.getByText(/Could not load your privacy summary/i)).toBeInTheDocument(),
  );
});

test("opening the page never triggers a Google sync", async () => {
  mockApi({ summary: summaryWith([googleConnection()]) });
  render(<ConnectionsPage />);
  await screen.findByTestId("data-inventory");
  // 32 no sync/disconnect POST fired from mounting/loading
  const calledPaths = apiMock.mock.calls.map((c) => c[0]);
  expect(calledPaths).toContain("/privacy/summary");
  expect(calledPaths).not.toContain("/connected-accounts/google/sync");
  expect(calledPaths).not.toContain("/connected-accounts/google/disconnect");
});

test("Gmail messages excluded for being outside Inbox/Sent are disclosed as by-design, not a failure", async () => {
  mockApi({ summary: summaryWith([googleConnection()]), sync: syncResult({ gmail_excluded: 74 }) });
  render(<ConnectionsPage />);
  await userEvent.setup().click(await screen.findByTestId("sync-google-now"));

  await waitFor(() => expect(screen.getByTestId("sync-result")).toBeInTheDocument());
  expect(screen.getByTestId("gmail-excluded-notice")).toHaveTextContent(
    "74 Gmail messages outside Inbox/Sent were not imported — by design, only Inbox and Sent are read.",
  );
  expect(screen.queryByTestId("calendar-incomplete-notice")).not.toBeInTheDocument();
});

test("Gmail messages that could not be fetched are disclosed as a genuine failure", async () => {
  mockApi({ summary: summaryWith([googleConnection()]), sync: syncResult({ gmail_incomplete: 1 }) });
  render(<ConnectionsPage />);
  await userEvent.setup().click(await screen.findByTestId("sync-google-now"));

  await waitFor(() => expect(screen.getByTestId("sync-result")).toBeInTheDocument());
  expect(screen.getByTestId("gmail-incomplete-notice")).toHaveTextContent(
    "1 Gmail message could not be read fully.",
  );
  expect(screen.queryByTestId("gmail-excluded-notice")).not.toBeInTheDocument();
});

test("calendar events that could not be parsed are disclosed distinctly", async () => {
  mockApi({
    summary: summaryWith([googleConnection()]),
    sync: syncResult({ calendar_incomplete: 1 }),
  });
  render(<ConnectionsPage />);
  await userEvent.setup().click(await screen.findByTestId("sync-google-now"));

  await waitFor(() => expect(screen.getByTestId("sync-result")).toBeInTheDocument());
  expect(screen.getByTestId("calendar-incomplete-notice")).toHaveTextContent(
    "1 calendar event could not be read fully.",
  );
  expect(screen.queryByTestId("gmail-excluded-notice")).not.toBeInTheDocument();
});

test("a disconnected account offers Connect Google again, not a dead Sync button, and keeps history", async () => {
  mockApi({
    summary: summaryWith([
      googleConnection({ status: "disconnected", connected: false, can_disconnect: false }),
    ]),
  });
  render(<ConnectionsPage />);

  await waitFor(() =>
    expect(screen.getByTestId("google-connection-status")).toHaveTextContent("disconnected"),
  );
  // Prior granted scopes stay visible (history not hidden).
  expect(screen.getByText("View Gmail evidence")).toBeInTheDocument();
  expect(screen.queryByTestId("sync-google-now")).not.toBeInTheDocument();
  expect(screen.queryByTestId("disconnect-google")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Connect Google" })).toBeInTheDocument();
});

test("disconnecting reloads the summary and shows the now-disconnected, data-retained state", async () => {
  let disconnected = false;
  mockApi({
    summary: () =>
      summaryWith([
        disconnected
          ? googleConnection({ status: "disconnected", connected: false, can_disconnect: false })
          : googleConnection(),
      ]),
  });
  // Make the disconnect POST flip the flag.
  const original = apiMock.getMockImplementation()!;
  apiMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path === "/connected-accounts/google/disconnect") {
      disconnected = true;
      return undefined;
    }
    return original(path, init);
  });

  render(<ConnectionsPage />);
  await userEvent.setup().click(await screen.findByTestId("disconnect-google"));

  await waitFor(() =>
    expect(screen.getByTestId("google-connection-status")).toHaveTextContent("disconnected"),
  );
  // Inventory counts (imported + derived) are unchanged by disconnect.
  expect(screen.getByTestId("inventory-source_items")).toHaveTextContent("42");
});

test("a fully clean sync shows no notices", async () => {
  mockApi({ summary: summaryWith([googleConnection()]), sync: syncResult({}) });
  render(<ConnectionsPage />);
  await userEvent.setup().click(await screen.findByTestId("sync-google-now"));

  await waitFor(() => expect(screen.getByTestId("sync-result")).toBeInTheDocument());
  expect(screen.queryByTestId("gmail-excluded-notice")).not.toBeInTheDocument();
  expect(screen.queryByTestId("gmail-incomplete-notice")).not.toBeInTheDocument();
  expect(screen.queryByTestId("calendar-incomplete-notice")).not.toBeInTheDocument();
});
