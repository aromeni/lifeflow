import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { ApiError } from "@/lib/api";
import type { AuditHistoryItem, AuditHistoryResponse, Me } from "@/lib/types";

import AuditHistoryPage from "./page";

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: apiMock };
});

const ME: Me = {
  id: "user-1",
  email: "person@example.com",
  display_name: "Person",
  timezone: "Europe/London",
  locale: "en-GB",
  onboarding_state: "complete",
};

function item(overrides: Partial<AuditHistoryItem> = {}): AuditHistoryItem {
  return {
    id: "event-1",
    occurred_at: "2026-07-22T08:30:00Z",
    category: "actions",
    actor: "you",
    title: "Action rejected",
    summary: "You chose not to approve an action.",
    tone: "warning",
    ...overrides,
  };
}

function history(
  items: AuditHistoryItem[],
  nextCursor: string | null = null,
): AuditHistoryResponse {
  return { items, next_cursor: nextCursor };
}

function mockApi(firstPage: AuditHistoryResponse) {
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/me") return ME;
    if (path.startsWith("/audit-history?")) return firstPage;
    throw new Error(`unexpected path ${path}`);
  });
}

beforeEach(() => {
  apiMock.mockReset();
});

test("renders privacy-safe plain language, actor, category, outcome and local time", async () => {
  mockApi(history([item()]));
  render(<AuditHistoryPage />);

  expect(await screen.findByRole("heading", { name: "Action rejected" })).toBeInTheDocument();
  expect(screen.getByText("You chose not to approve an action.")).toBeInTheDocument();
  expect(screen.getByText(/You · Actions · Attention/)).toBeInTheDocument();
  expect(screen.getByText(/22 Jul 2026/)).toBeInTheDocument();
  expect(screen.getByText(/Private content.*never shown here/i)).toBeInTheDocument();
  expect(screen.queryByText(/safe_metadata|entity_id|correlation_id/i)).toBeNull();
  expect(apiMock).toHaveBeenCalledWith("/audit-history?category=all&period=7d");
  expect(apiMock).toHaveBeenCalledWith("/me");
});

test("closed filters replace the first page and never reuse an old cursor", async () => {
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/me") return ME;
    if (path === "/audit-history?category=all&period=7d") return history([item()], "OLD-CURSOR");
    if (path === "/audit-history?category=briefs&period=7d")
      return history([
        item({
          id: "brief-1",
          category: "briefs",
          actor: "lifeflow",
          title: "Brief generated",
          summary: "LifeFlow prepared a new daily brief.",
          tone: "success",
        }),
      ]);
    throw new Error(`unexpected path ${path}`);
  });
  render(<AuditHistoryPage />);
  const user = userEvent.setup();

  await screen.findByRole("heading", { name: "Action rejected" });
  await user.selectOptions(screen.getByLabelText("Activity"), "briefs");

  expect(await screen.findByRole("heading", { name: "Brief generated" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Action rejected" })).toBeNull();
  expect(apiMock).toHaveBeenCalledWith("/audit-history?category=briefs&period=7d");
  expect(
    apiMock.mock.calls.some(
      ([path]) => typeof path === "string" && path.includes("cursor=OLD-CURSOR"),
    ),
  ).toBe(false);
});

test("load more appends a keyset page and keeps the cursor-bound filters", async () => {
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/me") return ME;
    if (path === "/audit-history?category=all&period=7d") return history([item()], "cursor value");
    if (path === "/audit-history?category=all&period=7d&cursor=cursor+value")
      return history([
        item({
          id: "event-2",
          title: "Brief generated",
          category: "briefs",
          actor: "lifeflow",
          summary: "LifeFlow prepared a new daily brief.",
          tone: "success",
        }),
      ]);
    throw new Error(`unexpected path ${path}`);
  });
  render(<AuditHistoryPage />);

  await userEvent.setup().click(await screen.findByRole("button", { name: "Load more" }));

  expect(await screen.findByRole("heading", { name: "Brief generated" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Action rejected" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
});

test("shows an honest empty state for the selected closed filters", async () => {
  mockApi(history([]));
  render(<AuditHistoryPage />);
  const user = userEvent.setup();

  expect(await screen.findByText(/No all activity was recorded/i)).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Time period"), "30d");

  await waitFor(() =>
    expect(apiMock).toHaveBeenCalledWith("/audit-history?category=all&period=30d"),
  );
});

test("handles unauthenticated and recoverable load failures accessibly", async () => {
  apiMock.mockImplementation(async (path: string) => {
    if (path.startsWith("/audit-history?")) {
      throw new ApiError(401, "unauthenticated", "Not signed in.");
    }
    if (path === "/me") return ME;
    throw new Error(`unexpected path ${path}`);
  });
  const { unmount } = render(<AuditHistoryPage />);
  expect(await screen.findByText(/You are not signed in/i)).toBeInTheDocument();
  unmount();

  apiMock.mockImplementation(async () => {
    throw new ApiError(500, "error", "Unavailable");
  });
  render(<AuditHistoryPage />);
  expect(await screen.findByText(/Could not load your audit history/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});
