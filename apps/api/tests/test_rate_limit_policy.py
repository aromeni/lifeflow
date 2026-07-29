"""Stage 9 Delivery Phase 4: the closed policy registry and its override
validation (ADR 0005 D64/D81)."""

import pytest

from lifeflow_api.rate_limit_policy import (
    POLICY_CODES,
    InvalidPolicyOverrideError,
    RateLimitPolicy,
    RateLimitSubjectType,
    effective_policy,
    get_policy,
    parse_policy_overrides,
)


def test_every_registered_policy_validates() -> None:
    for code in POLICY_CODES:
        policy = get_policy(code)
        assert policy.capacity > 0
        assert policy.refill_amount > 0
        assert policy.refill_window_seconds > 0
        assert policy.subject_type in (
            RateLimitSubjectType.authenticated_user,
            RateLimitSubjectType.client_ip,
        )


def test_unknown_policy_code_raises() -> None:
    with pytest.raises(KeyError):
        get_policy("not_a_real_policy")


@pytest.mark.parametrize("field", ["capacity", "refill_amount", "refill_window_seconds"])
def test_non_positive_field_rejected_at_construction(field: str) -> None:
    kwargs = {"capacity": 1, "refill_amount": 1, "refill_window_seconds": 1}
    kwargs[field] = 0
    with pytest.raises(ValueError, match="must be positive"):
        RateLimitPolicy("x", RateLimitSubjectType.client_ip, **kwargs)


def test_empty_overrides_string_yields_no_overrides() -> None:
    assert parse_policy_overrides("") == {}
    assert parse_policy_overrides("   ") == {}


def test_valid_override_replaces_only_named_fields() -> None:
    overrides = parse_policy_overrides('{"brief_generate": {"capacity": 1}}')
    original = get_policy("brief_generate")
    overridden = overrides["brief_generate"]
    assert overridden.capacity == 1
    assert overridden.refill_amount == original.refill_amount
    assert overridden.refill_window_seconds == original.refill_window_seconds


def test_override_malformed_json_fails() -> None:
    with pytest.raises(InvalidPolicyOverrideError):
        parse_policy_overrides("{not valid json")


def test_override_non_object_json_fails() -> None:
    with pytest.raises(InvalidPolicyOverrideError):
        parse_policy_overrides("[1, 2, 3]")


def test_override_unknown_policy_code_fails() -> None:
    with pytest.raises(InvalidPolicyOverrideError, match="Unknown"):
        parse_policy_overrides('{"totally_made_up_policy": {"capacity": 1}}')


def test_override_unknown_field_fails() -> None:
    with pytest.raises(InvalidPolicyOverrideError, match="unknown override field"):
        parse_policy_overrides('{"brief_generate": {"not_a_field": 1}}')


@pytest.mark.parametrize("bad_value", [0, -1, True, "10", 1.5])
def test_override_invalid_numeric_value_fails(bad_value: object) -> None:
    import json

    raw = json.dumps({"brief_generate": {"capacity": bad_value}})
    with pytest.raises(InvalidPolicyOverrideError):
        parse_policy_overrides(raw)


def test_effective_policy_falls_back_to_registry_default() -> None:
    policy = effective_policy("brief_generate", {})
    assert policy == get_policy("brief_generate")


def test_effective_policy_uses_override_when_present() -> None:
    overrides = parse_policy_overrides('{"brief_generate": {"capacity": 1}}')
    policy = effective_policy("brief_generate", overrides)
    assert policy.capacity == 1
