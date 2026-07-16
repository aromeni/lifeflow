import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import Home from "./page";

// TryDemoButton uses the app router, which has no provider under Vitest.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

test("home page states the product promise and demo path", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { level: 1, name: "LifeFlow AI" })).toBeInTheDocument();
  expect(screen.getByText(/prepares the next step — for your approval/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /try demo/i })).toBeInTheDocument();
});

test("home page shows the privacy summary", () => {
  render(<Home />);
  expect(
    screen.getByRole("heading", { level: 2, name: /how your data is handled/i }),
  ).toBeInTheDocument();
  expect(screen.getByText(/every action needs your approval/i)).toBeInTheDocument();
});
