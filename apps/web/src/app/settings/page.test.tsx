import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

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
  ],
};

beforeEach(() => {
  apiMock.mockReset();
});

function mockLoad() {
  apiMock.mockImplementation(async (path: string) => {
    if (path === "/me") return ME;
    if (path === "/preferences") return PREFERENCES;
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
  // Truthfulness: briefing time is stored but only becomes operational when
  // scheduled briefs arrive in a later phase.
  expect(screen.getByText(/not yet in use/i)).toBeInTheDocument();
  expect(screen.queryByTestId("settings-section-needs_attention")).not.toBeInTheDocument();
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
  const sectionsBody = JSON.parse(
    putCalls.find(([path]) => path === "/preferences/brief_sections")![1].body as string,
  );
  expect(sectionsBody.value.sections).toEqual(
    expect.arrayContaining(["today_upcoming", "waiting_for", "suggested_actions"]),
  );
});
