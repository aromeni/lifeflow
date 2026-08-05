import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import Home from "./page";

// TryDemoButton uses the app router, which has no provider under Vitest.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const { apiMock } = vi.hoisted(() => ({ apiMock: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: apiMock };
});

beforeEach(() => {
  apiMock.mockReset();
  // Default every test to disabled unless it says otherwise — matches the
  // fail-closed default the component itself starts from.
  apiMock.mockResolvedValue({
    google_provider_configured: false,
    google_oidc_signin_enabled: false,
    google_connector_oauth_enabled: false,
  });
});

test("home page states the product promise and demo path", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { level: 1, name: "LifeFlow AI" })).toBeInTheDocument();
  expect(
    screen.getByText(/prepares the next step — nothing is ever sent or changed/i),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /try demo/i })).toBeInTheDocument();
});

test("home page shows the privacy summary", () => {
  render(<Home />);
  expect(
    screen.getByRole("heading", { level: 2, name: /how your data is handled/i }),
  ).toBeInTheDocument();
  expect(screen.getByText(/never sends email/i)).toBeInTheDocument();
  expect(screen.getByText(/creates a gmail draft only after you approve/i)).toBeInTheDocument();
  expect(
    screen.getByText(/creates a new calendar event only after you approve/i),
  ).toBeInTheDocument();
  expect(screen.getByText(/never notifies guests/i)).toBeInTheDocument();
  expect(
    screen.getByText(/never modifies or deletes an existing calendar event/i),
  ).toBeInTheDocument();
});

test("no longer claims real Google integration arrives in a later stage", () => {
  render(<Home />);
  expect(screen.queryByText(/arrives in a later stage/i)).not.toBeInTheDocument();
});

test("distinguishes sign-in, connector consent, and demo mode", () => {
  render(<Home />);
  expect(
    screen.getByRole("heading", { level: 2, name: /three separate things, never confused/i }),
  ).toBeInTheDocument();
  expect(screen.getByText(/only confirms who you are/i)).toBeInTheDocument();
  expect(screen.getByText(/connecting gmail and calendar/i)).toBeInTheDocument();
  expect(
    screen.getByText(/entirely fictional data and needs no google account/i),
  ).toBeInTheDocument();
});

test("when Google sign-in is disabled, shows demo mode normally with a restrained dev-only note and no sign-in button", async () => {
  apiMock.mockResolvedValue({
    google_provider_configured: false,
    google_oidc_signin_enabled: false,
    google_connector_oauth_enabled: false,
  });
  render(<Home />);

  await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/config"));

  expect(screen.queryByTestId("sign-in-with-google")).not.toBeInTheDocument();
  expect(screen.getByTestId("google-sign-in-unavailable")).toHaveTextContent(
    /not enabled in this environment \(development only\)/i,
  );
  expect(screen.getByRole("button", { name: /try demo/i })).toBeInTheDocument();
});

test("when Google sign-in is enabled, shows a working Sign in with Google action using the real auth route", async () => {
  apiMock.mockResolvedValue({
    google_provider_configured: true,
    google_oidc_signin_enabled: true,
    google_connector_oauth_enabled: true,
  });
  render(<Home />);

  const link = await screen.findByTestId("sign-in-with-google");
  expect(link).toHaveAttribute("href", "http://localhost:8010/auth/google/login");
  expect(screen.getByRole("link", { name: /sign in with google/i })).toBeInTheDocument();
  expect(screen.queryByTestId("google-sign-in-unavailable")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /try demo/i })).toBeInTheDocument();
});

test("before the config response arrives, fails closed with no sign-in button", () => {
  apiMock.mockReturnValue(new Promise(() => {})); // never resolves
  render(<Home />);
  expect(screen.queryByTestId("sign-in-with-google")).not.toBeInTheDocument();
});

test("when the config request fails outright, fails closed with no sign-in button", async () => {
  apiMock.mockRejectedValue(new Error("network unavailable"));
  render(<Home />);
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/config"));
  expect(screen.queryByTestId("sign-in-with-google")).not.toBeInTheDocument();
  expect(screen.getByTestId("google-sign-in-unavailable")).toBeInTheDocument();
});

test("a malformed config response (missing capability field) fails closed, not enabled", async () => {
  // Simulates a broken/incomplete backend response — no exception thrown,
  // but the field this component reads is simply absent.
  apiMock.mockResolvedValue({} as unknown as { google_oidc_signin_enabled: boolean });
  render(<Home />);
  await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/config"));
  expect(screen.queryByTestId("sign-in-with-google")).not.toBeInTheDocument();
  expect(screen.getByTestId("google-sign-in-unavailable")).toBeInTheDocument();
});

test("Stage 11A Phase 6A.1: connector consent being enabled never displays Google sign-in — reproduces the exact Phase 6 incident configuration", async () => {
  // The exact flag combination that caused the Phase 6 incident: connector
  // consent authorised, OIDC sign-in not. The landing page's only Google
  // control (sign-in) must stay hidden regardless of the connector flag.
  apiMock.mockResolvedValue({
    google_provider_configured: true,
    google_oidc_signin_enabled: false,
    google_connector_oauth_enabled: true,
  });
  render(<Home />);

  await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/config"));
  expect(screen.queryByTestId("sign-in-with-google")).not.toBeInTheDocument();
  expect(screen.getByTestId("google-sign-in-unavailable")).toBeInTheDocument();
});

test("provider configured alone, with both flows disabled, never shows a sign-in button", async () => {
  apiMock.mockResolvedValue({
    google_provider_configured: true,
    google_oidc_signin_enabled: false,
    google_connector_oauth_enabled: false,
  });
  render(<Home />);

  await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/config"));
  expect(screen.queryByTestId("sign-in-with-google")).not.toBeInTheDocument();
});
