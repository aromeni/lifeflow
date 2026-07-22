"""Regression test for the .env.example secret-exposure incident (2026-07-21):
a real Google OAuth client secret was committed to this file and went
undetected because no gate ever ran against that commit (see
docs/security/threat-model.md, "Stage 8 Phase 2 focused remediation").

Loads scripts/check_env_example_secrets.py by file path rather than via
sys.path, since that script lives at the repo root, outside apps/api's
pythonpath.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_env_example_secrets.py"

spec = importlib.util.spec_from_file_location("check_env_example_secrets", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_module)
check = _module.check


def test_the_real_env_example_file_has_no_live_secrets() -> None:
    text = (REPO_ROOT / ".env.example").read_text()
    assert check(text) == []


def test_a_secret_shaped_variable_with_a_real_looking_value_fails() -> None:
    text = "SOME_OAUTH_CLIENT_SECRET=GOCSPX-fakeFakeFake123NotReal45\n"  # pragma: allowlist secret
    failures = check(text)
    assert len(failures) == 1
    assert "SOME_OAUTH_CLIENT_SECRET" in failures[0]


def test_a_secret_shaped_variable_left_empty_passes() -> None:
    assert check("SESSION_SECRET=\n") == []


def test_an_allow_listed_placeholder_value_passes() -> None:
    text = "GOOGLE_OIDC_CLIENT_SECRET=GOCSPX-your-oidc-client-secret\n"  # pragma: allowlist secret
    assert check(text) == []


def test_a_live_secret_format_is_flagged_even_under_an_unexpected_variable_name() -> None:
    failures = check("RANDOM_CONFIG_VALUE=AIzaFakeNotARealKeyAbc123\n")
    assert len(failures) == 1
    assert "RANDOM_CONFIG_VALUE" in failures[0]


def test_an_id_suffixed_variable_is_never_treated_as_secret_like() -> None:
    # TOKEN_KEY_ID and GOOGLE_OIDC_CLIENT_ID are identifiers, not secrets.
    assert check("TOKEN_KEY_ID=dev-1\n") == []
    assert check("GOOGLE_OIDC_CLIENT_ID=123-abc.apps.googleusercontent.com\n") == []


def test_comments_and_blank_lines_are_ignored() -> None:
    text = "# SOME_SECRET=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ted\n\nSESSION_SECRET=\n"
    assert check(text) == []
