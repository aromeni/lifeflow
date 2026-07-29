"""Stage 9 Delivery Phase 4 — the closed rate-limit policy registry (ADR 0005
D64, D81).

Every policy is a named, typed token bucket: `capacity` is the maximum number
of tokens the bucket can hold (the safe burst allowance — how many requests
may be issued back-to-back with no wait), and `refill_amount` tokens are added
per `refill_window_seconds` (the steady-state long-run rate). A bucket starts
full, so `capacity` also bounds the first burst. This is intentionally the
*only* place numeric limits live — no route file ever hard-codes a number.

Policies are looked up by a stable `code` string, never constructed ad hoc, so
a typo or unregistered code fails immediately and loudly (`KeyError`) rather
than silently applying no limit or a wrong one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from enum import StrEnum

# A bucket TTL cap so an idle key does not linger in Redis forever, and a
# floor so a very short window still leaves room for the atomic script to
# observe elapsed time meaningfully.
_MIN_BUCKET_TTL_SECONDS = 60
_MAX_BUCKET_TTL_SECONDS = 7 * 24 * 60 * 60


class RateLimitSubjectType(StrEnum):
    """How the bucket's subject is derived. Never a path parameter, account
    id, or proposal id — only these two closed choices."""

    authenticated_user = "authenticated_user"
    client_ip = "client_ip"


@dataclass(frozen=True)
class RateLimitPolicy:
    code: str
    subject_type: RateLimitSubjectType
    capacity: int
    refill_amount: int
    refill_window_seconds: int
    # Documents, rather than changes, behaviour: every policy in this pilot
    # charges a token even for a request that turns out to be an idempotent
    # replay (ADR 0005 D64 consequence) — broad request-volume control is a
    # separate concern from the database-level idempotency guard, which stays
    # authoritative regardless of whether the limiter allowed the request.
    applies_to_idempotent_replays: bool = True
    # A short, closed category the frontend can use to phrase guidance
    # without parsing the policy code itself.
    message_category: str = "general"

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError(f"{self.code}: capacity must be positive.")
        if self.refill_amount <= 0:
            raise ValueError(f"{self.code}: refill_amount must be positive.")
        if self.refill_window_seconds <= 0:
            raise ValueError(f"{self.code}: refill_window_seconds must be positive.")

    @property
    def refill_rate_per_second(self) -> float:
        return self.refill_amount / self.refill_window_seconds

    @property
    def bucket_ttl_seconds(self) -> int:
        # Long enough that a bucket mid-refill is never evicted early
        # (double the window), bounded so an abandoned key still expires.
        return max(
            _MIN_BUCKET_TTL_SECONDS, min(_MAX_BUCKET_TTL_SECONDS, self.refill_window_seconds * 2)
        )


# Pilot product defaults (not a legal or universal security standard) — see
# docs/architecture/adr/0005-stage9-privacy-hardening.md D81 and
# docs/delivery/reports/stage-09-phase-4.md for rationale per policy.
_REGISTRY: dict[str, RateLimitPolicy] = {
    p.code: p
    for p in (
        RateLimitPolicy(
            "anonymous_auth",
            RateLimitSubjectType.client_ip,
            capacity=5,
            refill_amount=10,
            refill_window_seconds=5 * 60,
            message_category="auth",
        ),
        RateLimitPolicy(
            "oauth_connect_callback",
            RateLimitSubjectType.authenticated_user,
            capacity=5,
            refill_amount=20,
            refill_window_seconds=10 * 60,
            message_category="connection",
        ),
        RateLimitPolicy(
            "demo_start",
            RateLimitSubjectType.authenticated_user,
            capacity=2,
            refill_amount=10,
            refill_window_seconds=60 * 60,
            message_category="write",
        ),
        RateLimitPolicy(
            "authenticated_read",
            RateLimitSubjectType.authenticated_user,
            capacity=60,
            refill_amount=300,
            refill_window_seconds=60,
            message_category="read",
        ),
        RateLimitPolicy(
            "privacy_audit_read",
            RateLimitSubjectType.authenticated_user,
            capacity=30,
            refill_amount=120,
            refill_window_seconds=60,
            message_category="read",
        ),
        RateLimitPolicy(
            "provider_sync",
            RateLimitSubjectType.authenticated_user,
            capacity=2,
            refill_amount=6,
            refill_window_seconds=15 * 60,
            message_category="sync",
        ),
        RateLimitPolicy(
            "brief_generate",
            RateLimitSubjectType.authenticated_user,
            capacity=3,
            refill_amount=12,
            refill_window_seconds=60 * 60,
            message_category="generation",
        ),
        RateLimitPolicy(
            "signal_extraction",
            RateLimitSubjectType.authenticated_user,
            capacity=3,
            refill_amount=12,
            refill_window_seconds=60 * 60,
            message_category="generation",
        ),
        RateLimitPolicy(
            "preference_memory_write",
            RateLimitSubjectType.authenticated_user,
            capacity=10,
            refill_amount=60,
            refill_window_seconds=60 * 60,
            message_category="write",
        ),
        RateLimitPolicy(
            "proposal_mutation",
            RateLimitSubjectType.authenticated_user,
            capacity=10,
            refill_amount=60,
            refill_window_seconds=60,
            message_category="write",
        ),
        RateLimitPolicy(
            "proposal_approval",
            RateLimitSubjectType.authenticated_user,
            capacity=5,
            refill_amount=30,
            refill_window_seconds=10 * 60,
            message_category="approval",
        ),
        RateLimitPolicy(
            "external_execution",
            RateLimitSubjectType.authenticated_user,
            capacity=2,
            refill_amount=10,
            refill_window_seconds=10 * 60,
            message_category="execution",
        ),
        RateLimitPolicy(
            "deletion_preview",
            RateLimitSubjectType.authenticated_user,
            capacity=2,
            refill_amount=10,
            refill_window_seconds=60 * 60,
            message_category="deletion",
        ),
        RateLimitPolicy(
            "deletion_confirm_cancel",
            RateLimitSubjectType.authenticated_user,
            capacity=1,
            refill_amount=5,
            refill_window_seconds=60 * 60,
            message_category="deletion",
        ),
        RateLimitPolicy(
            "account_deletion_preview",
            RateLimitSubjectType.authenticated_user,
            capacity=1,
            refill_amount=3,
            refill_window_seconds=24 * 60 * 60,
            message_category="deletion",
        ),
        RateLimitPolicy(
            "account_deletion_confirm",
            RateLimitSubjectType.authenticated_user,
            capacity=1,
            refill_amount=3,
            refill_window_seconds=24 * 60 * 60,
            message_category="deletion",
        ),
    )
}

POLICY_CODES = frozenset(_REGISTRY)

_OVERRIDABLE_FIELDS = ("capacity", "refill_amount", "refill_window_seconds")


def get_policy(code: str) -> RateLimitPolicy:
    """Look up a registered policy. Raises KeyError for an unregistered
    code — callers must never construct a policy ad hoc."""
    try:
        return _REGISTRY[code]
    except KeyError:
        raise KeyError(f"Unregistered rate-limit policy code: {code!r}") from None


class InvalidPolicyOverrideError(ValueError):
    pass


def parse_policy_overrides(raw_json: str) -> dict[str, RateLimitPolicy]:
    """Validate `RATE_LIMIT_POLICY_OVERRIDES_JSON` into a
    {policy_code: overridden RateLimitPolicy} map. Empty string means no
    overrides. Raises InvalidPolicyOverrideError for anything else invalid:
    malformed JSON, a non-object body, an unregistered policy code, an
    unknown field, a non-integer value, or a non-positive value — this must
    fail configuration validation at startup, never apply silently."""
    if not raw_json.strip():
        return {}
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise InvalidPolicyOverrideError(
            f"RATE_LIMIT_POLICY_OVERRIDES_JSON is not valid JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise InvalidPolicyOverrideError("RATE_LIMIT_POLICY_OVERRIDES_JSON must be a JSON object.")

    overrides: dict[str, RateLimitPolicy] = {}
    for code, fields in parsed.items():
        if code not in _REGISTRY:
            raise InvalidPolicyOverrideError(
                f"Unknown rate-limit policy code in overrides: {code!r}"
            )
        if not isinstance(fields, dict):
            raise InvalidPolicyOverrideError(
                f"{code}: override must be a JSON object of numeric fields."
            )
        unknown = set(fields) - set(_OVERRIDABLE_FIELDS)
        if unknown:
            raise InvalidPolicyOverrideError(
                f"{code}: unknown override field(s) {sorted(unknown)}."
            )
        base = _REGISTRY[code]
        numeric: dict[str, int] = {
            "capacity": base.capacity,
            "refill_amount": base.refill_amount,
            "refill_window_seconds": base.refill_window_seconds,
        }
        for field in _OVERRIDABLE_FIELDS:
            if field not in fields:
                continue
            value = fields[field]
            if isinstance(value, bool) or not isinstance(value, int):
                raise InvalidPolicyOverrideError(f"{code}.{field} must be a positive integer.")
            if value <= 0:
                raise InvalidPolicyOverrideError(f"{code}.{field} must be a positive integer.")
            numeric[field] = value
        try:
            overrides[code] = replace(
                base,
                capacity=numeric["capacity"],
                refill_amount=numeric["refill_amount"],
                refill_window_seconds=numeric["refill_window_seconds"],
            )
        except ValueError as exc:
            raise InvalidPolicyOverrideError(str(exc)) from exc
    return overrides


def effective_policy(code: str, overrides: dict[str, RateLimitPolicy]) -> RateLimitPolicy:
    return overrides.get(code, get_policy(code))


__all__ = [
    "POLICY_CODES",
    "InvalidPolicyOverrideError",
    "RateLimitPolicy",
    "RateLimitSubjectType",
    "effective_policy",
    "get_policy",
    "parse_policy_overrides",
]
