"""Stage 8 Phase 3: the pure inferred-memory registry, deny-list, sign-off
extractor, and deterministic confidence model (ADR 0004 D52-D54).

Everything here is pure (no database, Redis, or LLM), so these are ordinary
unit tests — not integration-marked.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from lifeflow_api.memory_registry import (
    CONFIDENCE_EXPIRY_FLOOR,
    DEFAULT_SIGNOFF,
    MEMORY_REGISTRY,
    PREFERRED_EMAIL_SIGNOFF_KEY,
    PROHIBITED_MEMORY_CATEGORIES,
    Observation,
    UnknownMemoryKeyError,
    confidence_band,
    effective_confidence,
    evaluate_observations,
    evidence_fingerprint,
    extract_signoff,
    is_registered,
    require_spec,
)

NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)


def _obs(value: str, *, days_ago: float = 0.0, pid: uuid.UUID | None = None) -> Observation:
    return Observation(
        source_proposal_id=pid or uuid.uuid4(),
        value=value,
        observed_at=NOW - timedelta(days=days_ago),
    )


# --- Registry & deny-list (tests 1, 3) -------------------------------------


def test_only_preferred_email_signoff_is_registered() -> None:
    assert set(MEMORY_REGISTRY) == {PREFERRED_EMAIL_SIGNOFF_KEY}
    assert is_registered(PREFERRED_EMAIL_SIGNOFF_KEY)


def test_unknown_memory_key_fails_closed() -> None:
    for key in ("", "favourite_colour", "priority_weights", "SIGNOFF"):
        assert not is_registered(key)
        with pytest.raises(UnknownMemoryKeyError):
            require_spec(key)


def test_every_prohibited_category_fails_closed() -> None:
    # The closed registry already makes these unreachable; the deny-list turns
    # "we happen not to infer this" into "we refuse to", regression-guarded.
    assert PROHIBITED_MEMORY_CATEGORIES  # non-empty
    for category in PROHIBITED_MEMORY_CATEGORIES:
        assert not is_registered(category)
        with pytest.raises(UnknownMemoryKeyError):
            require_spec(category)


def test_prohibited_covers_the_required_sensitive_categories() -> None:
    required = {
        "health",
        "disability",
        "race",
        "religion",
        "political_opinion",
        "sexuality",
        "biometric",
        "trade_union_membership",
        "criminal_conviction",
        "financial_hardship",
        "immigration_status",
        "psychological_diagnosis",
        "intimate_relationship_status",
        "children",
        "personality",
        "mood",
        "risk_profile",
    }
    assert required <= PROHIBITED_MEMORY_CATEGORIES


def test_registered_spec_is_suggest_only_and_low_sensitivity() -> None:
    spec = require_spec(PREFERRED_EMAIL_SIGNOFF_KEY)
    assert spec.application_mode == "suggest_only"
    assert spec.sensitivity == "low"
    assert spec.min_evidence >= 2
    assert spec.corresponding_preference_key == PREFERRED_EMAIL_SIGNOFF_KEY


# --- Sign-off extraction (test 12 building block, D53) ----------------------


def test_extracts_recognised_signoffs_case_insensitively() -> None:
    assert extract_signoff("Hi,\n\nThanks for this.\n\nKind regards") == "Kind regards"
    assert extract_signoff("body\n\nbest") == "Best"
    assert extract_signoff("body\n\nMANY THANKS,") == "Many thanks"


def test_ignores_quoted_and_contact_lines() -> None:
    # A quoted original message is not the user's own writing.
    assert extract_signoff("Best\n\n> On Tuesday you wrote:\n> Regards") == "Best"
    # Contact-bearing signature lines below the sign-off are skipped, so the
    # recognised closing line is still found.
    assert extract_signoff("Kind regards\njane@example.com") == "Kind regards"
    assert extract_signoff("Regards\nCall me on 07700 900000") == "Regards"


def test_a_trailing_name_line_defeats_extraction_conservatively() -> None:
    # A bare name below the sign-off is neither quoted nor contact-bearing, so
    # the extractor stops there and returns None rather than scanning upward
    # and risking a false match mid-body. LifeFlow-composed evidence drafts end
    # with the sign-off token itself, so this conservatism costs nothing.
    assert extract_signoff("Kind regards\nJane Doe") is None


def test_unrecognised_closing_yields_no_observation() -> None:
    # Free text can never enter the memory tables — an unrecognised closing
    # line ends the search with None (D53).
    assert extract_signoff("body\n\nTTYL") is None
    assert extract_signoff("body\n\nSee you at the thing") is None
    assert extract_signoff("") is None


def test_default_signoff_is_best() -> None:
    assert DEFAULT_SIGNOFF == "Best"


# --- Confidence model (tests 4, 6, 7, 10, 11 building blocks; D54) ----------


def test_confidence_is_bounded_and_banded() -> None:
    result = evaluate_observations([_obs("Best")], now=NOW)
    assert result is not None
    assert 0.0 <= result.confidence <= 1.0
    assert confidence_band(0.1) == "low"
    assert confidence_band(0.5) == "medium"
    assert confidence_band(0.9) == "high"


def test_confidence_band_boundaries_are_pinned() -> None:
    """The band cut-points are a deliberate, documented contract (ADR 0004
    D54), not an aesthetic choice — pin them so they can't drift. 0.750 → High
    (the value the manual smoke observed) is deliberate: High is ≥ 0.67."""
    # Medium floor at 0.34 (inclusive), Low just below.
    assert confidence_band(0.339) == "low"
    assert confidence_band(0.34) == "medium"
    # High floor at 0.67 (inclusive), Medium just below.
    assert confidence_band(0.669) == "medium"
    assert confidence_band(0.67) == "high"
    # The specific value the smoke test produced.
    assert confidence_band(0.750) == "high"


def test_effective_confidence_decays_with_time_only() -> None:
    """A candidate keeps losing confidence with the passage of time alone —
    no recompute or user action required (ADR 0004 D54)."""
    evaluated = datetime(2026, 7, 1, tzinfo=UTC)
    stored = 0.80
    # Same instant → no decay.
    assert effective_confidence(stored, evaluated, evaluated) == stored
    # One 30-day half-life later → halved.
    one_hl = evaluated + timedelta(days=30)
    assert abs(effective_confidence(stored, evaluated, one_hl) - 0.40) < 1e-9
    # Two half-lives → quartered.
    two_hl = evaluated + timedelta(days=60)
    assert abs(effective_confidence(stored, evaluated, two_hl) - 0.20) < 1e-9
    # Far future → below the expiry floor.
    assert effective_confidence(stored, evaluated, evaluated + timedelta(days=365)) < (
        CONFIDENCE_EXPIRY_FLOOR
    )
    # Never negative; a missing evaluation timestamp means no decay.
    assert effective_confidence(stored, None, one_hl) == stored
    assert 0.0 <= effective_confidence(stored, evaluated, two_hl) <= 1.0


def test_no_observations_returns_none() -> None:
    assert evaluate_observations([], now=NOW) is None


def test_one_observation_never_reaches_high_confidence() -> None:
    # strength = 1/4 = 0.25, so a single fresh observation caps at 0.25 — low
    # band, and below MIN_EVIDENCE it is never surfaced as active (skill §7).
    result = evaluate_observations([_obs("Best")], now=NOW)
    assert result is not None
    assert result.evidence_count == 1
    assert result.confidence <= 0.25
    assert confidence_band(result.confidence) == "low"


def test_repeated_consistent_observations_increase_confidence() -> None:
    one = evaluate_observations([_obs("Best")], now=NOW)
    four = evaluate_observations([_obs("Best") for _ in range(4)], now=NOW)
    assert one is not None and four is not None
    assert four.confidence > one.confidence
    assert four.evidence_count == 4
    # Fresh + fully consistent + saturated strength → high.
    assert confidence_band(four.confidence) == "high"


def test_contradictory_observations_reduce_confidence_and_pick_dominant() -> None:
    consistent = evaluate_observations([_obs("Best") for _ in range(3)], now=NOW)
    mixed = evaluate_observations([_obs("Best"), _obs("Best"), _obs("Regards")], now=NOW)
    assert consistent is not None and mixed is not None
    assert mixed.value == "Best"  # dominant
    assert mixed.total_observations == 3
    assert mixed.evidence_count == 2  # only the agreeing ones
    assert mixed.confidence < consistent.confidence  # consistency < 1 lowers it


def test_old_evidence_decays() -> None:
    fresh = evaluate_observations([_obs("Best") for _ in range(4)], now=NOW)
    stale = evaluate_observations([_obs("Best", days_ago=90) for _ in range(4)], now=NOW)
    assert fresh is not None and stale is not None
    # 90 days = three 30-day half-lives → freshness ≈ 0.125, big drop.
    assert stale.confidence < fresh.confidence * 0.2


def test_fingerprint_is_stable_and_changes_with_new_evidence() -> None:
    p1, p2, p3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    a = evidence_fingerprint("Best", [p1, p2])
    b = evidence_fingerprint("Best", [p2, p1])  # order-independent
    c = evidence_fingerprint("Best", [p1, p2, p3])  # materially new evidence
    assert a == b
    assert a != c
