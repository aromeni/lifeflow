#!/usr/bin/env python3
"""Fail if .github/workflows/ci.yml stops running one of the two Playwright
end-to-end suites this repository maintains: the original demo-journey suite
(`pnpm web:e2e`, `apps/web/e2e`) and the Stage 9 Delivery Phase 5 outage-
resilience suite (`./scripts/e2e-resilience.sh`, `apps/web/e2e-resilience`).

Added during Stage 9 Final Integration after an audit found the resilience
suite had been built, verified, and documented on `stage-9-resilience-
telemetry` but was never wired into any CI workflow — nothing would have
caught it silently disappearing again in a future edit. Deliberately narrow
and textual, matching the style of scripts/check_uvicorn_launch_safety.py:
this is not a YAML/job-graph validator, just a guard that both known
invocation strings are still present somewhere in the workflow file.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_INVOCATIONS = (
    "pnpm web:e2e",
    "./scripts/e2e-resilience.sh",
)


def main() -> int:
    if not CI_WORKFLOW.is_file():
        print(f"{CI_WORKFLOW}: not found")
        return 1
    text = CI_WORKFLOW.read_text()
    missing = [invocation for invocation in REQUIRED_INVOCATIONS if invocation not in text]
    if missing:
        print("ci.yml is missing required E2E suite invocation(s):")
        for invocation in missing:
            print(" -", invocation)
        return 1
    print("Both required Playwright E2E suites are wired into ci.yml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
