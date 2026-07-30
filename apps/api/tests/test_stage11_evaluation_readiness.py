"""Stage 11 evaluation-readiness validator (docs/evaluation/stage-11/synthetic-scenario-manifest.md).

Static checks only: no browser, no live demo stack, no participant data.
Confirms the synthetic dataset the Round 1 evaluation manifest cites is
actually fictional and actually contains the scenario IDs the manifest
names, so the manifest cannot silently drift from the real fixtures.
"""

import json
from importlib import resources
from pathlib import Path

REAL_WORLD_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "yahoo.com",
    "icloud.com",
    "me.com",
    "aol.com",
    "protonmail.com",
}
ALLOWED_DOMAIN_SUFFIXES = (".example", "lifeflow.local")

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DOC = REPO_ROOT / "docs" / "evaluation" / "stage-11" / "synthetic-scenario-manifest.md"


def _load_demo_json(filename: str) -> list[dict]:  # type: ignore[type-arg]
    package = resources.files("lifeflow_api.demo.data").joinpath("v1")
    return json.loads(package.joinpath(filename).read_text("utf-8"))  # type: ignore[no-any-return]


def _all_email_domains() -> set[str]:
    emails = _load_demo_json("emails.json")
    domains: set[str] = set()
    for email in emails:
        domains.add(email["from_email"].rsplit("@", 1)[-1].lower())
        for recipient in email.get("to", []):
            domains.add(recipient.rsplit("@", 1)[-1].lower())
    return domains


def test_no_real_world_email_domain_in_demo_dataset() -> None:
    domains = _all_email_domains()
    assert domains.isdisjoint(REAL_WORLD_EMAIL_DOMAINS), (
        f"Real-world email domain(s) found in the demo dataset: "
        f"{domains & REAL_WORLD_EMAIL_DOMAINS}"
    )


def test_every_demo_domain_is_reserved_or_local() -> None:
    domains = _all_email_domains()
    unexpected = {d for d in domains if not d.endswith(ALLOWED_DOMAIN_SUFFIXES)}
    assert not unexpected, f"Unexpected non-fictional domain(s): {unexpected}"


def test_manifest_scenario_keys_exist_in_demo_manifest() -> None:
    package = resources.files("lifeflow_api.demo.data").joinpath("v1")
    demo_manifest = json.loads(package.joinpath("manifest.json").read_text("utf-8"))
    expected_keys = {
        "explicit_request",
        "near_deadline",
        "overdue_follow_up",
        "calendar_conflict",
        "newsletter_deprioritise",
        "prompt_injection",
        "ambiguous_low_confidence",
        "proposed_gmail_draft_material",
        "proposed_calendar_event_material",
    }
    assert expected_keys.issubset(demo_manifest["scenarios"].keys())


def test_manifest_referenced_email_and_event_ids_exist() -> None:
    package = resources.files("lifeflow_api.demo.data").joinpath("v1")
    demo_manifest = json.loads(package.joinpath("manifest.json").read_text("utf-8"))
    emails = _load_demo_json("emails.json")
    events = _load_demo_json("events.json")
    known_email_ids = {e["id"] for e in emails}
    known_event_ids = {e["id"] for e in events}

    referenced_email_ids: set[str] = set()
    referenced_event_ids: set[str] = set()
    for ids in demo_manifest["scenarios"].values():
        for scenario_id in ids:
            if scenario_id.startswith("em-"):
                referenced_email_ids.add(scenario_id)
            elif scenario_id.startswith("ev-"):
                referenced_event_ids.add(scenario_id)

    assert referenced_email_ids.issubset(known_email_ids)
    assert referenced_event_ids.issubset(known_event_ids)


def test_evaluation_manifest_doc_exists_and_cites_real_scenario_ids() -> None:
    assert MANIFEST_DOC.is_file(), f"Missing {MANIFEST_DOC}"
    text = MANIFEST_DOC.read_text("utf-8")
    package = resources.files("lifeflow_api.demo.data").joinpath("v1")
    demo_manifest = json.loads(package.joinpath("manifest.json").read_text("utf-8"))
    known_ids = {i for ids in demo_manifest["scenarios"].values() for i in ids}
    cited_known_ids = {scenario_id for scenario_id in known_ids if scenario_id in text}
    assert cited_known_ids, "Manifest doc cites none of the known demo scenario IDs"


def test_no_real_oauth_credential_required_for_demo_dataset_load() -> None:
    """The demo dataset itself is a static fixture: loading it must never
    require a Google OAuth credential or an Anthropic API key."""
    emails = _load_demo_json("emails.json")
    events = _load_demo_json("events.json")
    assert emails and events
