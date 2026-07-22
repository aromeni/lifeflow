"""The closed, typed inferred-memory registry (ADR 0004 D52-D54).

Everything in this module is pure and unit-tested: the registry of eligible
memory types, the prohibited-category deny-list, the deterministic confidence
model, and the sign-off extractor. Nothing here touches the database, Redis,
or an LLM.

Safety by construction:
- only keys in `MEMORY_REGISTRY` exist; unknown and sensitive keys fail closed
  (there is no free-text key/value path anywhere);
- values are composed from recognised, normalised tokens — never from
  arbitrary user input;
- confidence is arithmetic over evidence rows, never a model score.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

# ---------------------------------------------------------------------------
# Prohibited categories (skill §4 sensitive-inference prohibition, ADR D52)
# ---------------------------------------------------------------------------
# A documented, tested deny-list. The closed registry below already makes
# these unreachable (only registered keys exist), but naming them explicitly
# turns "we happen not to infer this" into "we refuse to infer this", and a
# regression test pins that none of them can ever be registered.
PROHIBITED_MEMORY_CATEGORIES: frozenset[str] = frozenset(
    {
        "health",
        "medical_status",
        "disability",
        "race",
        "ethnicity",
        "religion",
        "belief",
        "political_opinion",
        "sexuality",
        "sex_life",
        "biometric",
        "trade_union_membership",
        "criminal_allegation",
        "criminal_conviction",
        "financial_hardship",
        "creditworthiness",
        "immigration_status",
        "protected_characteristic",
        "psychological_diagnosis",
        "intimate_relationship_status",
        "children",
        "vulnerable_person",
        "personality",
        "mood",
        "risk_profile",
    }
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
ApplicationMode = Literal["suggest_only"]
SensitivityClass = Literal["low", "sensitive"]

PREFERRED_EMAIL_SIGNOFF_KEY = "preferred_email_signoff"
EVIDENCE_TYPE_SIGNOFF = "gmail_draft_signoff_edit"
REASON_APPROVED_EDITED_DRAFT = "approved_edited_draft"


@dataclass(frozen=True)
class MemoryTypeSpec:
    """The closed contract for one inferred-memory type."""

    key: str
    evidence_type: str
    # Minimum agreeing observations before a candidate is surfaced as
    # reviewable/confirmable — one observation can never create an active
    # memory (skill §7).
    min_evidence: int
    application_mode: ApplicationMode
    # The explicit preference key a confirmation writes to (the only channel
    # through which this memory can ever affect behaviour, D55).
    corresponding_preference_key: str
    sensitivity: SensitivityClass
    explanation_template: str

    def explanation(self, value: str, evidence_count: int) -> str:
        return self.explanation_template.format(value=value, count=evidence_count)


MEMORY_REGISTRY: dict[str, MemoryTypeSpec] = {
    PREFERRED_EMAIL_SIGNOFF_KEY: MemoryTypeSpec(
        key=PREFERRED_EMAIL_SIGNOFF_KEY,
        evidence_type=EVIDENCE_TYPE_SIGNOFF,
        min_evidence=2,
        application_mode="suggest_only",
        corresponding_preference_key=PREFERRED_EMAIL_SIGNOFF_KEY,
        sensitivity="low",
        explanation_template=(
            'You ended {count} draft replies with "{value}" after editing them, so '
            "LifeFlow suggests using it as your sign-off. It is only a suggestion until "
            "you confirm it — nothing you send changes on its own."
        ),
    )
}

MEMORY_KEYS: tuple[str, ...] = tuple(MEMORY_REGISTRY)


class UnknownMemoryKeyError(KeyError):
    """Raised for any key not in the closed registry (fails closed)."""


def require_spec(memory_key: str) -> MemoryTypeSpec:
    if memory_key in PROHIBITED_MEMORY_CATEGORIES or memory_key not in MEMORY_REGISTRY:
        raise UnknownMemoryKeyError(memory_key)
    return MEMORY_REGISTRY[memory_key]


def is_registered(memory_key: str) -> bool:
    return memory_key in MEMORY_REGISTRY and memory_key not in PROHIBITED_MEMORY_CATEGORIES


# ---------------------------------------------------------------------------
# Sign-off extraction (ADR 0004 D53)
# ---------------------------------------------------------------------------
# A closed set of recognised sign-offs mapped to a single canonical spelling.
# Only these ever become evidence; an unrecognised closing line yields no
# observation at all, so free text can never enter the memory tables.
_CANONICAL_SIGNOFFS: dict[str, str] = {
    "best": "Best",
    "best regards": "Best regards",
    "best wishes": "Best wishes",
    "kind regards": "Kind regards",
    "warm regards": "Warm regards",
    "regards": "Regards",
    "thanks": "Thanks",
    "many thanks": "Many thanks",
    "thank you": "Thank you",
    "cheers": "Cheers",
    "sincerely": "Sincerely",
    "yours sincerely": "Yours sincerely",
    "yours faithfully": "Yours faithfully",
}

RECOGNISED_SIGNOFFS: tuple[str, ...] = tuple(dict.fromkeys(_CANONICAL_SIGNOFFS.values()))

# The default the composer uses when there is no confirmed sign-off (D57).
DEFAULT_SIGNOFF = "Best"


def _looks_like_contact_line(line: str) -> bool:
    """A signature line carrying contact details — never treated as a
    sign-off (D53: ignore signatures containing contact details)."""
    lowered = line.lower()
    if "@" in line or "http://" in lowered or "https://" in lowered or "www." in lowered:
        return True
    return any(character.isdigit() for character in line)


def extract_signoff(body: str) -> str | None:
    """Return the canonical sign-off a draft body ends with, or None.

    Reads only the trailing closing line: scans the last non-empty lines from
    the bottom, skipping quoted text (`>`) and contact-bearing signature
    lines, and returns the first that matches a recognised sign-off. The rest
    of the body is never inspected or stored (D53)."""
    if not body:
        return None
    lines = [line.strip() for line in body.replace("\r\n", "\n").split("\n")]
    for line in reversed(lines):
        if not line:
            continue
        if line.startswith(">"):
            # Quoted original message — not the user's own writing.
            continue
        if _looks_like_contact_line(line):
            continue
        candidate = line.rstrip(",.!;: ").lower()
        if candidate in _CANONICAL_SIGNOFFS:
            return _CANONICAL_SIGNOFFS[candidate]
        # A non-empty, non-quoted, non-contact line that is not a recognised
        # sign-off ends the search: the closing is not one we learn from.
        return None
    return None


# ---------------------------------------------------------------------------
# Confidence model (ADR 0004 D54)
# ---------------------------------------------------------------------------
# confidence = evidence_strength * consistency * freshness, each in [0, 1].
_EVIDENCE_STRENGTH_TARGET = 4  # agreeing observations at which strength saturates
_FRESHNESS_HALF_LIFE = timedelta(days=30)
# Below this confidence a surfaced candidate is considered decayed and expires
# (its evidence is too old/thin to keep suggesting). Confirmed explicit
# preferences never decay — they live in the preference table, not here.
CONFIDENCE_EXPIRY_FLOOR = 0.15

ConfidenceBand = Literal["low", "medium", "high"]
_BAND_MEDIUM_MIN = 0.34
_BAND_HIGH_MIN = 0.67


def confidence_band(confidence: float) -> ConfidenceBand:
    if confidence >= _BAND_HIGH_MIN:
        return "high"
    if confidence >= _BAND_MEDIUM_MIN:
        return "medium"
    return "low"


def effective_confidence(
    stored_confidence: float,
    last_evaluated_at: datetime | None,
    now: datetime,
) -> float:
    """A candidate's confidence *right now*, continuing the 30-day half-life
    decay from the moment it was last evaluated (ADR 0004 D54) — so a memory
    that has sat untouched keeps losing confidence with the passage of time
    alone, never depending on a later recompute or user action to reflect
    reality.

    `stored_confidence` already baked in freshness up to `last_evaluated_at`
    (recompute set `last_evaluated_at = now` at that time); multiplying by
    `0.5 ** ((now - last_evaluated_at) / 30d)` extends that same curve without
    double-counting. Confirmed explicit preferences never decay and must not
    be passed here — they are not candidates."""
    if last_evaluated_at is None:
        return max(0.0, min(1.0, stored_confidence))
    age_days = max((now - last_evaluated_at).total_seconds(), 0.0) / 86_400.0
    half_life_days = _FRESHNESS_HALF_LIFE.total_seconds() / 86_400.0
    decay: float = 0.5 ** (age_days / half_life_days)
    return max(0.0, min(1.0, stored_confidence * decay))


@dataclass(frozen=True)
class Observation:
    """One normalised evidence point used by the confidence model."""

    source_proposal_id: uuid.UUID | None
    value: str
    observed_at: datetime


@dataclass(frozen=True)
class InferenceResult:
    """The deterministic outcome of evaluating a set of observations."""

    value: str
    confidence: float
    evidence_count: int  # observations agreeing with the dominant value
    total_observations: int
    first_observed_at: datetime
    last_observed_at: datetime
    fingerprint: str


def _dominant_value(observations: Iterable[Observation]) -> str:
    """The most-observed value; ties broken by the most recent observation,
    then lexically, so the result is deterministic."""
    by_value: dict[str, list[Observation]] = {}
    for observation in observations:
        by_value.setdefault(observation.value, []).append(observation)

    def sort_key(item: tuple[str, list[Observation]]) -> tuple[int, datetime, str]:
        value, group = item
        latest = max(observation.observed_at for observation in group)
        return (len(group), latest, value)

    return max(by_value.items(), key=sort_key)[0]


def evidence_fingerprint(value: str, proposal_ids: Iterable[uuid.UUID | None]) -> str:
    """A stable hash of the contributing evidence set (dominant value + the
    sorted proposal ids that agree). Dismissal records this; a candidate is
    only reconsidered once the fingerprint changes (materially new evidence,
    D55)."""
    ids = sorted(str(pid) for pid in proposal_ids if pid is not None)
    material = value + "|" + "|".join(ids)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def evaluate_observations(
    observations: list[Observation], *, now: datetime
) -> InferenceResult | None:
    """Reduce raw observations to a single inferred value with deterministic
    confidence, or None if there are no observations.

    - dominant value = the most-observed sign-off (deterministic tie-break);
    - evidence_strength = min(1, agreeing / 4);
    - consistency = agreeing / total;
    - freshness = 0.5 ** (age_of_latest_agreeing / 30 days);
    - confidence = the product, clamped to [0, 1].
    """
    if not observations:
        return None
    value = _dominant_value(observations)
    agreeing = [obs for obs in observations if obs.value == value]
    total = len(observations)
    agreeing_count = len(agreeing)

    strength = min(1.0, agreeing_count / _EVIDENCE_STRENGTH_TARGET)
    consistency = agreeing_count / total
    latest_agreeing = max(obs.observed_at for obs in agreeing)
    age = now - latest_agreeing
    age_days = max(age.total_seconds(), 0.0) / 86_400.0
    freshness = 0.5 ** (age_days / (_FRESHNESS_HALF_LIFE.total_seconds() / 86_400.0))

    confidence = max(0.0, min(1.0, strength * consistency * freshness))
    return InferenceResult(
        value=value,
        confidence=confidence,
        evidence_count=agreeing_count,
        total_observations=total,
        first_observed_at=min(obs.observed_at for obs in agreeing),
        last_observed_at=latest_agreeing,
        fingerprint=evidence_fingerprint(value, (obs.source_proposal_id for obs in agreeing)),
    )


__all__ = [
    "CONFIDENCE_EXPIRY_FLOOR",
    "DEFAULT_SIGNOFF",
    "EVIDENCE_TYPE_SIGNOFF",
    "MEMORY_KEYS",
    "MEMORY_REGISTRY",
    "PREFERRED_EMAIL_SIGNOFF_KEY",
    "PROHIBITED_MEMORY_CATEGORIES",
    "REASON_APPROVED_EDITED_DRAFT",
    "RECOGNISED_SIGNOFFS",
    "ConfidenceBand",
    "InferenceResult",
    "MemoryTypeSpec",
    "Observation",
    "UnknownMemoryKeyError",
    "confidence_band",
    "effective_confidence",
    "evaluate_observations",
    "evidence_fingerprint",
    "extract_signoff",
    "is_registered",
    "require_spec",
]
