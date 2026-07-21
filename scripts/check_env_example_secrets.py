#!/usr/bin/env python3
"""Fail if .env.example contains a value that looks like a live secret.

Added after a real Google OAuth client secret was committed to .env.example
(commit d8a6de1) and went undetected because no gate ever ran against that
commit: the local pre-commit hook is opt-in per clone, and CI's secret-scan
job only triggers on pushes to `main` and pull requests, not on direct
pushes to feature branches (see docs/security/threat-model.md). This script
is a fast, current-tree, branch-agnostic check specifically for the example
config file, wired into both pre-commit and a branch-agnostic CI workflow
so a future paste-in of a real credential cannot slip through the same gap.

Deliberately narrow: this is not a general secret scanner (detect-secrets
and gitleaks already cover that). It only asserts that secret-shaped
variables in this one file hold an explicit, known-safe placeholder.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"

# Variable names ending in these must hold an allow-listed placeholder, not
# a real value. `_ID` suffixes (TOKEN_KEY_ID, GOOGLE_OIDC_CLIENT_ID) are
# identifiers, not secrets, and are excluded even if they also match SECRET/KEY.
SECRET_LIKE_NAME = re.compile(r"(SECRET|TOKEN|PASSWORD|_KEY)$", re.IGNORECASE)
IDENTIFIER_SUFFIX = re.compile(r"_ID$", re.IGNORECASE)

# Explicit known-safe values used in this file today. A new secret-like
# variable must add its placeholder here deliberately — never widen this to
# a heuristic like "starts with your-", which a real secret could also match
# if someone prefixed it that way by mistake.
ALLOWED_PLACEHOLDER_VALUES = {
    "",
    "dev-1",
    "GOCSPX-your-oidc-client-secret",
    "GOCSPX-your-connector-client-secret",
}

# Known vendor secret-format prefixes, checked against every value in the
# file regardless of variable name, as defense in depth.
LIVE_SECRET_PREFIXES = (
    "GOCSPX-",
    "AIza",
    "sk-",
    "ghp_",
    "gho_",
    "glpat-",
    "AKIA",
    "xox",
)


def check(text: str) -> list[str]:
    failures: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, _, raw_value = stripped.partition("=")
        name = name.strip()
        value = raw_value.split("#", 1)[0].strip()

        if SECRET_LIKE_NAME.search(name) and not IDENTIFIER_SUFFIX.search(name):
            if value not in ALLOWED_PLACEHOLDER_VALUES:
                failures.append(f"line {lineno}: {name} has a non-placeholder value")
                continue

        if value not in ALLOWED_PLACEHOLDER_VALUES and any(
            value.startswith(prefix) for prefix in LIVE_SECRET_PREFIXES
        ):
            failures.append(f"line {lineno}: {name} value matches a live secret format")

    return failures


def main() -> int:
    failures = check(ENV_EXAMPLE.read_text())
    if failures:
        print(".env.example contains values that do not look like safe placeholders:")
        for failure in failures:
            print(" -", failure)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
