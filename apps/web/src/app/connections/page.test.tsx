import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import type { ConnectedAccountsResponse, GoogleSyncResult } from "@/lib/types";

import ConnectionsPage from "./page";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: apiMock };
});

const CONNECTED_RESPONSE: ConnectedAccountsResponse = {
  accounts: [
    {
      provider: "google",
      status: "active",
      granted_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      last_sync_at: null,
    },
  ],
};

const DISCONNECTED_RESPONSE: ConnectedAccountsResponse = {
  accounts: [
    {
      provider: "google",
      status: "disconnected",
      granted_scopes: ["https://www.googleapis.com/auth/gmail.readonly"],
      last_sync_at: "2026-07-20T06:30:00Z",
    },
  ],
};

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

beforeEach(() => {
  apiMock.mockReset();
});

test("Gmail messages excluded for being outside Inbox/Sent are disclosed as by-design, not a failure", async () => {
  apiMock.mockResolvedValueOnce(CONNECTED_RESPONSE); // initial /connected-accounts load
  apiMock.mockResolvedValueOnce(syncResult({ gmail_excluded: 74 })); // sync POST
  apiMock.mockResolvedValueOnce(CONNECTED_RESPONSE); // reload after sync

  render(<ConnectionsPage />);
  await userEvent.setup().click(await screen.findByTestId("sync-google-now"));

  await waitFor(() => expect(screen.getByTestId("sync-result")).toBeInTheDocument());
  expect(screen.getByTestId("gmail-excluded-notice")).toHaveTextContent(
    "74 Gmail messages outside Inbox/Sent were not imported — by design, only Inbox and Sent are read.",
  );
  expect(screen.queryByTestId("calendar-incomplete-notice")).not.toBeInTheDocument();
});

test("Gmail messages that could not be fetched are disclosed as a genuine failure, distinct from by-design exclusions", async () => {
  apiMock.mockResolvedValueOnce(CONNECTED_RESPONSE);
  apiMock.mockResolvedValueOnce(syncResult({ gmail_incomplete: 1 }));
  apiMock.mockResolvedValueOnce(CONNECTED_RESPONSE);

  render(<ConnectionsPage />);
  await userEvent.setup().click(await screen.findByTestId("sync-google-now"));

  await waitFor(() => expect(screen.getByTestId("sync-result")).toBeInTheDocument());
  expect(screen.getByTestId("gmail-incomplete-notice")).toHaveTextContent(
    "1 Gmail message could not be read fully.",
  );
  expect(screen.queryByTestId("gmail-excluded-notice")).not.toBeInTheDocument();
  expect(screen.queryByTestId("calendar-incomplete-notice")).not.toBeInTheDocument();
});

test("calendar events that could not be parsed are disclosed distinctly from excluded Gmail messages", async () => {
  apiMock.mockResolvedValueOnce(CONNECTED_RESPONSE);
  apiMock.mockResolvedValueOnce(syncResult({ calendar_incomplete: 1 }));
  apiMock.mockResolvedValueOnce(CONNECTED_RESPONSE);

  render(<ConnectionsPage />);
  await userEvent.setup().click(await screen.findByTestId("sync-google-now"));

  await waitFor(() => expect(screen.getByTestId("sync-result")).toBeInTheDocument());
  expect(screen.getByTestId("calendar-incomplete-notice")).toHaveTextContent(
    "1 calendar event could not be read fully.",
  );
  expect(screen.queryByTestId("gmail-excluded-notice")).not.toBeInTheDocument();
});

test("a previously-connected but now-disconnected account offers Connect Google again, not a dead Sync button", async () => {
  apiMock.mockResolvedValueOnce(DISCONNECTED_RESPONSE);

  render(<ConnectionsPage />);

  await waitFor(() =>
    expect(screen.getByTestId("google-connection-status")).toHaveTextContent("disconnected"),
  );
  // History stays visible — status, prior scopes, and last sync are not hidden.
  expect(screen.getByText(/gmail.readonly/)).toBeInTheDocument();
  expect(screen.getByText(/2026-07-20T06:30:00Z/)).toBeInTheDocument();
  // But the only action offered is reconnecting — never a Sync/Disconnect
  // button that can no longer do anything against a dead token.
  expect(screen.queryByTestId("sync-google-now")).not.toBeInTheDocument();
  expect(screen.queryByText("Disconnect Google")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Connect Google" })).toBeInTheDocument();
});

test("a fully clean sync shows no notices", async () => {
  apiMock.mockResolvedValueOnce(CONNECTED_RESPONSE);
  apiMock.mockResolvedValueOnce(syncResult({}));
  apiMock.mockResolvedValueOnce(CONNECTED_RESPONSE);

  render(<ConnectionsPage />);
  await userEvent.setup().click(await screen.findByTestId("sync-google-now"));

  await waitFor(() => expect(screen.getByTestId("sync-result")).toBeInTheDocument());
  expect(screen.queryByTestId("gmail-excluded-notice")).not.toBeInTheDocument();
  expect(screen.queryByTestId("gmail-incomplete-notice")).not.toBeInTheDocument();
  expect(screen.queryByTestId("calendar-incomplete-notice")).not.toBeInTheDocument();
});
