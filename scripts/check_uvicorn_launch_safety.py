#!/usr/bin/env python3
"""Fail if a repository-controlled Uvicorn launch command for this
application does not explicitly set a safe forwarded-header trust posture.

Added after Stage 9 Delivery Phase 4 (ADR 0005 D64/D81) discovered — during
the phase's required manual smoke test, not any automated test — that
Uvicorn's own `--proxy-headers`/`--forwarded-allow-ips` default trusts
X-Forwarded-For from any loopback connection, silently rewriting
`request.client` before this application's own `TRUSTED_PROXY_CIDRS`
resolver (`rate_limit_ip.py`) ever sees the request. Every live launch site
was fixed to pass `--forwarded-allow-ips=""` (empty — trust nothing at the
Uvicorn layer; the application's own resolver is the real security boundary,
never Uvicorn's independent header trust). This script exists so a future
launcher (a new script, a Dockerfile, a CI step) cannot silently regress that
fix.

Deliberately narrow and exact-list, not a line-by-line command parser: launch
commands appear in several different syntaxes across this repository (a
shell one-liner in README.md/CLAUDE.md/demo.sh, a TypeScript template string
in playwright.config.ts, a Python argv list in the real-Uvicorn regression
test, and a docstring in main.py), so this checks per-file "does this file
document/issue a launch of this app's Uvicorn server, and if so does it also
carry the safe flag somewhere in it" rather than matching one command syntax.
That is sufficient at this repository's current scale (each listed file
contains exactly one canonical launch command) without being fragile across
formats.

Archived, point-in-time historical reports (Stage 8's completion report and
manual checklist) are excluded by exact name, not a wildcard: they are frozen
records of what was actually run *at the time* (repository convention — see
CLAUDE.md, "Complete only the active stage... Archive every completion
report") and predate this flag's existence entirely, since Stage 8 finished
before Stage 9's rate limiting (and therefore TRUSTED_PROXY_CIDRS) existed at
all. Rewriting them would misrepresent history rather than correct a live
defect.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every file in the repository that currently documents or issues a real
# launch command for this application's Uvicorn server. Adding a new
# launcher (a Dockerfile, a new script, a new CI step) requires adding it
# here deliberately — `find_unlisted_launch_sites` below cross-checks this
# list against a live, repo-wide search and fails if a launch-shaped file is
# missing from it, so a new site cannot silently go unchecked.
KNOWN_LAUNCH_SITES = (
    "README.md",
    "CLAUDE.md",
    "scripts/demo.sh",
    "apps/api/src/lifeflow_api/main.py",
    "apps/web/playwright.config.ts",
    "apps/api/tests/test_rate_limit_uvicorn_regression.py",
    "scripts/e2e-resilience.sh",
    "apps/web/e2e-resilience/journey-b-uncertain-write.spec.ts",
)

# Frozen historical records — see module docstring. Exact list, no wildcard,
# so a future archived report is not accidentally exempted by pattern.
FROZEN_HISTORICAL_PATHS = (
    "docs/delivery/reports/stage-08.md",
    "docs/delivery/stage-08-phase-2-manual-checklist.md",
)

_APP_TARGET = "lifeflow_api.main:app"
_SAFE_FLAG = "--forwarded-allow-ips"


def _mentions_app_launch(text: str) -> bool:
    return "uvicorn" in text and _APP_TARGET in text


def _has_safe_flag(text: str) -> bool:
    return _SAFE_FLAG in text


def check_known_sites() -> list[str]:
    failures: list[str] = []
    for rel_path in KNOWN_LAUNCH_SITES:
        path = REPO_ROOT / rel_path
        if not path.is_file():
            failures.append(f"{rel_path}: listed as a known launch site but no longer exists")
            continue
        text = path.read_text(errors="replace")
        if not _mentions_app_launch(text):
            failures.append(
                f"{rel_path}: listed as a known launch site but no longer documents/issues "
                f"a Uvicorn launch of {_APP_TARGET} — remove it from KNOWN_LAUNCH_SITES "
                "if it genuinely no longer launches the app"
            )
        elif not _has_safe_flag(text):
            failures.append(
                f"{rel_path}: documents/issues a Uvicorn launch of {_APP_TARGET} without "
                f"an explicit {_SAFE_FLAG} value (ADR 0005 D64/D81)"
            )
    return failures


def find_unlisted_launch_sites() -> list[str]:
    """Repo-wide cross-check over tracked AND untracked files (a brand-new,
    not-yet-committed launcher must still be caught): any file mentioning a
    Uvicorn launch of this app that is neither in KNOWN_LAUNCH_SITES nor
    FROZEN_HISTORICAL_PATHS must be classified deliberately, not silently
    skipped."""
    known = set(KNOWN_LAUNCH_SITES) | set(FROZEN_HISTORICAL_PATHS)
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    # This script's own file path: it necessarily contains both markers in
    # its docstring/source while describing the rule, not while launching
    # anything.
    self_path = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()

    unlisted: list[str] = []
    for rel_path in result.stdout.splitlines():
        if rel_path in known or rel_path == self_path:
            continue
        full = REPO_ROOT / rel_path
        if not full.is_file():
            continue
        try:
            text = full.read_text(errors="replace")
        except OSError:
            continue
        if _mentions_app_launch(text):
            unlisted.append(rel_path)
    return unlisted


def main() -> int:
    failures = check_known_sites()
    for rel_path in find_unlisted_launch_sites():
        failures.append(
            f"{rel_path}: documents/issues a Uvicorn launch of {_APP_TARGET} but is not "
            "classified in scripts/check_uvicorn_launch_safety.py (add it to "
            "KNOWN_LAUNCH_SITES or, only if it is a frozen historical record predating "
            "ADR 0005 D64/D81, to FROZEN_HISTORICAL_PATHS)"
        )

    if failures:
        print("Unsafe or unclassified Uvicorn launch site(s) found:")
        for failure in failures:
            print(" -", failure)
        return 1
    print(f"All {len(KNOWN_LAUNCH_SITES)} known Uvicorn launch sites set a safe proxy posture.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
