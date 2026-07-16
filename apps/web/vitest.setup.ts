import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest runs without injected globals, so RTL's automatic cleanup does not
// register itself; do it explicitly to keep tests isolated.
afterEach(cleanup);
