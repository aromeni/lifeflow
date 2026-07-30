#!/usr/bin/env python3
"""Fail if .github/workflows/ci.yml stops actually running one of the three
Playwright end-to-end suites this repository maintains: the original demo-
journey suite (`./scripts/e2e.sh`, `apps/web/e2e`), the Stage 9 Delivery
Phase 5 outage-resilience suite (`./scripts/e2e-resilience.sh`, `apps/web/
e2e-resilience`), and the Stage 10 design/accessibility/responsive/visual-
regression suite (`./scripts/e2e-design.sh`, `apps/web/e2e-design`). All
three must run through their wrapper script — a raw `pnpm web:e2e`/
`playwright test` invocation skips the real ARQ worker and Redis the first
two depend on (a genuine CI defect found and fixed during Stage 9 Final
Integration: several journeys failed in the very first real CI run because
the job provisioned neither).

Added during Stage 9 Final Integration after an audit found the resilience
suite had been built, verified, and documented on `stage-9-resilience-
telemetry` but was never wired into any CI workflow — nothing would have
caught it silently disappearing again in a future edit. Extended during
Stage 10 final closure after the same class of gap recurred in miniature:
the three new design/accessibility/responsive/visual-regression specs were
initially placed inside the original `apps/web/e2e` discovery boundary,
silently inflating that suite's reported journey count rather than being
independently countable. Deliberately narrow and textual, matching the
style of scripts/check_uvicorn_launch_safety.py: this is not a YAML/job-
graph validator, just a guard that all three known invocation strings
appear as an actual `run:` step, not merely in a comment.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_RUN_STEPS = (
    "./scripts/e2e.sh",
    "./scripts/e2e-resilience.sh",
    "./scripts/e2e-design.sh",
)


def _run_step_commands(text: str) -> list[str]:
    """Extract the command text of every `- run: ...` step, ignoring
    comments — a script name mentioned only in prose must not satisfy this
    check."""
    return re.findall(r"^\s*-\s*run:\s*(.+)$", text, re.MULTILINE)


def main() -> int:
    if not CI_WORKFLOW.is_file():
        print(f"{CI_WORKFLOW}: not found")
        return 1
    text = CI_WORKFLOW.read_text()
    commands = _run_step_commands(text)
    missing = [step for step in REQUIRED_RUN_STEPS if not any(step in cmd for cmd in commands)]
    if missing:
        print("ci.yml is missing required E2E suite invocation(s) as an actual run step:")
        for step in missing:
            print(" -", step)
        return 1
    print("All three required Playwright E2E suites are wired into ci.yml as real run steps.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
