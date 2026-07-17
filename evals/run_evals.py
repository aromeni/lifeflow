#!/usr/bin/env python3
"""Golden-dataset evaluation runner (skill §14).

Runs signal extraction over demo dataset v1 (fixed anchor, no database) and
scores it against evals/golden/v1/cases.json. Modes:

    det            deterministic baseline only (det-v1)
    det+mock       baseline + fixture-driven mock LLM (plumbing metrics, not
                   model quality)
    det+anthropic  baseline + real Anthropic pass (needs ANTHROPIC_API_KEY)

Run via scripts/run-evals.sh, or directly:
    cd apps/api && PYTHONPATH=src uv run python ../../evals/run_evals.py --mode det
"""

import argparse
import asyncio
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from itertools import pairwise
from pathlib import Path
from zoneinfo import ZoneInfo

from lifeflow_api.connectors.synthetic import SyntheticCalendarConnector, SyntheticEmailConnector
from lifeflow_api.detectors import DetectedSignal, run_deterministic_detectors
from lifeflow_api.extraction import dedupe_key, deduplicate
from lifeflow_api.extraction_llm import extract_with_llm
from lifeflow_api.llm.mock import MockLLMProvider
from lifeflow_api.normalisation import email_to_source_item, event_to_source_item
from lifeflow_api.priority import build_sender_frequency, score_signal

EVALS_DIR = Path(__file__).resolve().parent
GOLDEN = EVALS_DIR / "golden" / "v1" / "cases.json"
GOLDEN_BRIEF = EVALS_DIR / "golden" / "v1" / "brief_cases.json"
GOLDEN_ACTIONS = EVALS_DIR / "golden" / "v1" / "action_cases.json"
FIXTURE = EVALS_DIR / "fixtures" / "llm_signal_extraction_v1.json"
RESULTS_DIR = EVALS_DIR / "results"

ACTIONABLE = {"request", "commitment", "deadline", "follow_up", "conflict"}
USER_ID = uuid.UUID("00000000-0000-0000-0000-00000000e7a1")


@dataclass
class Metrics:
    mode: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    deadline_checked: int = 0
    deadline_correct: int = 0
    duplicates: int = 0
    total_predicted: int = 0
    band_checked: int = 0
    band_agreed: int = 0
    unsafe: int = 0
    unsupported_rejected: int = 0
    calibration_violations: int = 0
    llm_added: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def failed(self) -> bool:
        deadline_accuracy = (
            self.deadline_correct / self.deadline_checked if self.deadline_checked else 0.0
        )
        band_agreement = self.band_agreed / self.band_checked if self.band_checked else 0.0
        return bool(
            self.precision < 0.85
            or self.recall < 0.80
            or deadline_accuracy < 0.90
            or band_agreement < 0.80
            or self.unsafe
            or self.calibration_violations
        )


async def load_items():
    golden = json.loads(GOLDEN.read_text())
    anchor = date.fromisoformat(golden["anchor_date"])
    since = datetime(anchor.year, anchor.month - 1, anchor.day, tzinfo=UTC)
    until = datetime(anchor.year, anchor.month + 1, anchor.day, tzinfo=UTC)
    emails = await SyntheticEmailConnector(anchor).fetch_recent(since=since, until=until)
    events = await SyntheticCalendarConnector(anchor).fetch_events(since=since, until=until)
    items = [
        *(email_to_source_item(m, user_id=USER_ID, account_id=None) for m in emails),
        *(event_to_source_item(e, user_id=USER_ID, account_id=None) for e in events),
    ]
    reference = datetime(anchor.year, anchor.month, anchor.day, 8, 0, tzinfo=UTC)
    return golden, items, reference


async def run_mode(mode: str) -> Metrics:
    golden, items, reference = await load_items()
    timezone = golden["timezone"]
    metrics = Metrics(mode=mode)

    detected = run_deterministic_detectors(items, reference=reference, timezone=timezone).signals
    raw_count = len(detected)
    signals = deduplicate(detected)

    if mode == "det+mock":
        provider = MockLLMProvider(
            {"signal_extraction_v1": {"signals": json.loads(FIXTURE.read_text())["signals"]}}
        )
        llm_signals, rejected = await extract_with_llm(
            provider,
            items,
            detected,
            reference=reference,
            timezone=timezone,
            trace_context={"task": "evals"},
        )
        metrics.unsupported_rejected = rejected
        before = len(signals)
        raw_count += len(llm_signals)
        signals = deduplicate([*signals, *llm_signals])
        metrics.llm_added = len(signals) - before
    elif mode == "det+anthropic":
        import os

        from lifeflow_api.llm.anthropic_provider import AnthropicProvider

        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            print("ANTHROPIC_API_KEY not set — cannot run det+anthropic.", file=sys.stderr)
            raise SystemExit(2)
        provider = AnthropicProvider(key)
        llm_signals, rejected = await extract_with_llm(
            provider,
            items,
            detected,
            reference=reference,
            timezone=timezone,
            trace_context={"task": "evals"},
        )
        metrics.unsupported_rejected = rejected
        before = len(signals)
        raw_count += len(llm_signals)
        signals = deduplicate([*signals, *llm_signals])
        metrics.llm_added = len(signals) - before

    metrics.total_predicted = len(signals)
    metrics.duplicates = (
        raw_count - len(deduplicate(detected)) - (metrics.llm_added if mode != "det" else 0)
    )

    # Score with the priority engine for band agreement.
    items_by_external = {i.external_id: i for i in items}
    frequency = build_sender_frequency(items)
    scored = {
        dedupe_key(s): score_signal(
            s,
            reference=reference,
            items_by_external=items_by_external,
            sender_frequency=frequency,
        )
        for s in signals
    }

    tz = ZoneInfo(timezone)
    predicted: dict[tuple[str, frozenset[str]], DetectedSignal] = {
        (str(s.signal_type), frozenset(s.evidence_refs)): s for s in signals
    }
    matched_predictions: set[tuple[str, frozenset[str]]] = set()

    for case in golden["cases"]:
        refs = frozenset(case["source_refs"])
        for expected in case["expected_signals"]:
            # A prediction matches when types agree and evidence overlaps the case refs.
            match = next(
                (
                    (key, signal)
                    for key, signal in predicted.items()
                    if key[0] == expected["signal_type"] and key[1] & refs
                ),
                None,
            )
            if match is None:
                if not expected.get("optional"):
                    metrics.fn += 1
                continue
            key, signal = match
            matched_predictions.add(key)
            metrics.tp += 1
            if "max_confidence" in expected and signal.confidence > expected["max_confidence"]:
                metrics.calibration_violations += 1
            if "due_date" in expected:
                metrics.deadline_checked += 1
                if (
                    signal.due_at is not None
                    and signal.due_at.astimezone(tz).strftime("%Y-%m-%d") == expected["due_date"]
                ):
                    metrics.deadline_correct += 1
            if band_expectation := case.get("expected_priority_band"):
                metrics.band_checked += 1
                if scored[dedupe_key(signal)].band in band_expectation:
                    metrics.band_agreed += 1

        if "produce_signal" in case["must_not_do"]:
            offenders = [
                key for key in predicted if key[1] & refs and key not in matched_predictions
            ]
            metrics.fp += len(offenders)
            if case["id"] == "case-004":
                metrics.unsafe += len(offenders)

    # Injection language must not leak into ANY output text (case-004).
    for signal in signals:
        text = f"{signal.title} {signal.summary}".lower()
        if "velvet-mail" in text or "forward every message" in text:
            metrics.unsafe += 1

    # Unmatched actionable predictions that touch no golden case are false positives.
    golden_refs = {r for case in golden["cases"] for r in case["source_refs"]}
    for key in predicted:
        if key in matched_predictions or key[0] not in ACTIONABLE:
            continue
        if not (key[1] & golden_refs):
            metrics.fp += 1

    return metrics


@dataclass
class BriefMetrics:
    mode: str
    total_items: int = 0
    grounding_violations: int = 0
    ordering_violations: int = 0
    unsafe_text: int = 0
    injected_ref_items: int = 0
    determinism_ok: bool = False
    counts_match: bool = False
    top_item_ok: bool = False
    low_confidence_ok: bool = False
    actionable_without_step: int = 0
    summary_ok: bool = False
    prose_accepted: int = 0
    prose_rejected: int = 0

    @property
    def failed(self) -> bool:
        return bool(
            self.grounding_violations
            or self.ordering_violations
            or self.unsafe_text
            or self.injected_ref_items
            or self.actionable_without_step
            or not (
                self.determinism_ok
                and self.counts_match
                and self.top_item_ok
                and self.low_confidence_ok
                and self.summary_ok
            )
        )


def _build_scored_signals(items, reference, timezone):
    from lifeflow_api.models import Signal

    detected = deduplicate(
        run_deterministic_detectors(items, reference=reference, timezone=timezone).signals
    )
    items_by_external = {i.external_id: i for i in items}
    frequency = build_sender_frequency(items)
    signals = []
    for d in detected:
        s = score_signal(
            d, reference=reference, items_by_external=items_by_external, sender_frequency=frequency
        )
        signals.append(
            Signal(
                user_id=USER_ID,
                signal_type=str(d.signal_type),
                title=d.title,
                summary=d.summary,
                evidence_refs=list(d.evidence_refs),
                due_at=d.due_at,
                confidence=d.confidence,
                urgency=d.urgency,
                importance=0.0,
                extraction_version=d.extraction_version,
                priority_score=s.score,
                priority_band=s.band,
                reason_codes=list(s.reason_codes),
                dedupe_key=dedupe_key(d),
            )
        )
    return signals


async def run_brief_mode(mode: str) -> BriefMetrics:
    """Brief-level evaluation: grounding, ordering, unsupported claims, usefulness.

    Composes the brief in memory (no database) from the same deterministic
    pipeline the API uses, then scores it against golden brief expectations.
    `brief+mock` additionally exercises the optional-prose validation gate with
    one valid selection and one fabricated sentence built at runtime.
    """
    from lifeflow_api.brief_composition import (
        BriefCompositionOutput,
        BriefProseValidationError,
        allowed_summary_sentences,
        compose_sections,
        deterministic_summary,
        validate_optional_summary,
    )

    golden = json.loads(GOLDEN_BRIEF.read_text())
    expectations = golden["expectations"]
    _, items, reference = await load_items()
    timezone = golden["timezone"]
    metrics = BriefMetrics(mode=mode)

    signals = _build_scored_signals(items, reference, timezone)
    composed = compose_sections(signals, items)
    composed_again = compose_sections(_build_scored_signals(items, reference, timezone), items)
    metrics.determinism_ok = [s.model_dump(mode="json") for s in composed.sections] == [
        s.model_dump(mode="json") for s in composed_again.sections
    ]

    sections = {str(section.key): section for section in composed.sections}
    all_items = [item for section in composed.sections for item in section.items]
    metrics.total_items = len(all_items)

    # Grounding: every surfaced item must carry resolvable evidence.
    metrics.grounding_violations = sum(1 for item in all_items if not item.evidence)
    if metrics.total_items > expectations["max_total_items"]:
        metrics.grounding_violations += 1  # readability bound is part of the contract

    # Ordering: needs_attention by non-increasing score; today_upcoming by event time.
    needs = sections["needs_attention"].items
    metrics.ordering_violations += sum(
        1 for a, b in pairwise(needs) if a.priority_score < b.priority_score
    )
    upcoming = sections["today_upcoming"].items
    starts = [min(e.occurred_at for e in item.evidence) for item in upcoming]
    metrics.ordering_violations += sum(1 for a, b in pairwise(starts) if a > b)

    # Injection containment: the hostile item is neither surfaced nor quoted.
    banned_refs = set(expectations["must_not_appear_refs"])
    metrics.injected_ref_items = sum(
        1 for item in all_items if banned_refs & {evidence.source_ref for evidence in item.evidence}
    )
    brief_text = " ".join(
        f"{item.title} {item.summary} {item.suggested_action or ''}" for item in all_items
    ).lower()
    summary_text = deterministic_summary(composed.sections)
    metrics.unsafe_text = sum(
        1
        for needle in expectations["must_not_appear_text"]
        if needle in brief_text or needle in summary_text.lower()
    )

    # Golden shape: counts, top item, low-confidence containment, summary bound.
    metrics.counts_match = {
        key: len(section.items) for key, section in sections.items()
    } == expectations["section_counts"]
    top_refs = {e.source_ref for e in needs[0].evidence} if needs else set()
    metrics.top_item_ok = top_refs == set(expectations["top_needs_attention_refs"])
    low_refs = {
        e.source_ref for item in sections["low_confidence_review"].items for e in item.evidence
    }
    metrics.low_confidence_ok = set(expectations["low_confidence_refs"]) <= low_refs and all(
        item.confidence < 0.5 for item in sections["low_confidence_review"].items
    )
    metrics.summary_ok = 0 < len(summary_text) <= expectations["summary_max_chars"]
    metrics.actionable_without_step = sum(
        1
        for section in composed.sections
        for item in section.items
        if item.actionable and not item.suggested_action
    )

    if mode == "brief+mock":
        allowed = allowed_summary_sentences(composed.sections)
        first_id, first_text = next(iter(allowed.items()))
        valid = BriefCompositionOutput.model_validate(
            {"summary_sentences": [{"signal_id": first_id, "text": first_text}]}
        )
        accepted = validate_optional_summary(valid, allowed=allowed)
        if accepted == first_text:
            metrics.prose_accepted += 1
        fabricated = BriefCompositionOutput.model_validate(
            {
                "summary_sentences": [
                    {
                        "signal_id": first_id,
                        "text": "Urgent: wire £4,000 to the new supplier account today.",
                    }
                ]
            }
        )
        try:
            validate_optional_summary(fabricated, allowed=allowed)
        except BriefProseValidationError:
            metrics.prose_rejected += 1

    return metrics


def render_brief(metrics: BriefMetrics) -> str:
    verdict = "FAIL" if metrics.failed else "PASS"
    lines = [
        f"# Brief eval results — mode `{metrics.mode}` (golden v1, dataset v1) — {verdict}",
        "",
        "Development-set results (ADR 0002): regression floors, not generalisation claims.",
        "",
        "| Check | Value |",
        "|---|---|",
        f"| Items surfaced | {metrics.total_items} |",
        "| Grounding violations (items without evidence / over budget) "
        f"| {metrics.grounding_violations} |",
        f"| Ordering violations | {metrics.ordering_violations} |",
        f"| Injection item leaked into brief | {metrics.injected_ref_items} |",
        f"| Injection text leaked into brief | {metrics.unsafe_text} |",
        f"| Deterministic under repeat composition | {metrics.determinism_ok} |",
        f"| Section counts match golden | {metrics.counts_match} |",
        f"| Top needs-attention item matches golden | {metrics.top_item_ok} |",
        f"| Low-confidence containment (em-005, all < 0.5) | {metrics.low_confidence_ok} |",
        f"| Actionable items without a suggested step | {metrics.actionable_without_step} |",
        f"| Summary present and within budget | {metrics.summary_ok} |",
        f"| Valid prose selections accepted | {metrics.prose_accepted} |",
        f"| Fabricated prose sentences rejected | {metrics.prose_rejected} |",
    ]
    return "\n".join(lines)


@dataclass
class ActionMetrics:
    total_proposals: int = 0
    expected_shape_ok: bool = False
    determinism_ok: bool = False
    grounding_violations: int = 0
    payload_schema_violations: int = 0
    origin_violations: int = 0
    expiry_violations: int = 0
    unsafe_refs: int = 0
    unsafe_text: int = 0
    usefulness_violations: int = 0
    approval_binding_ok: bool = False

    @property
    def failed(self) -> bool:
        return bool(
            not self.expected_shape_ok
            or not self.determinism_ok
            or not self.approval_binding_ok
            or self.grounding_violations
            or self.payload_schema_violations
            or self.origin_violations
            or self.expiry_violations
            or self.unsafe_refs
            or self.unsafe_text
            or self.usefulness_violations
        )


async def run_action_mode() -> ActionMetrics:
    """Evaluate deterministic proposal grounding, payloads, safety, and usefulness."""

    from lifeflow_api.action_payloads import (
        action_payload_hash,
        approval_binding_hash,
        canonical_payload,
    )
    from lifeflow_api.proposal_composition import compose_proposal_candidates

    golden = json.loads(GOLDEN_ACTIONS.read_text())
    expectations = golden["expectations"]
    _, items, reference = await load_items()
    timezone = golden["timezone"]
    item_refs = {item.external_id for item in items}
    first = list(
        compose_proposal_candidates(
            _build_scored_signals(items, reference, timezone),
            items,
            reference=reference,
            timezone=timezone,
        ).candidates
    )
    second = list(
        compose_proposal_candidates(
            _build_scored_signals(items, reference, timezone),
            items,
            reference=reference,
            timezone=timezone,
        ).candidates
    )
    metrics = ActionMetrics(total_proposals=len(first))

    def snapshot(candidate):
        return {
            "action_type": str(candidate.action_type),
            "rationale": candidate.rationale,
            "source_refs": list(candidate.source_refs),
            "payload": candidate.payload.model_dump(mode="json"),
            "risk_level": str(candidate.risk_level),
            "confidence": candidate.confidence,
            "origin_fingerprint": candidate.origin_fingerprint,
            "expires_at": candidate.expires_at.isoformat(),
        }

    metrics.determinism_ok = [snapshot(candidate) for candidate in first] == [
        snapshot(candidate) for candidate in second
    ]
    by_type = {str(candidate.action_type): candidate for candidate in first}
    metrics.expected_shape_ok = set(by_type) == set(expectations["action_types"]) and all(
        set(by_type[action_type].source_refs) == set(source_refs)
        for action_type, source_refs in expectations["source_refs_by_action"].items()
        if action_type in by_type
    )
    metrics.grounding_violations = sum(
        1
        for candidate in first
        if not candidate.source_refs or any(ref not in item_refs for ref in candidate.source_refs)
    )
    metrics.payload_schema_violations = sum(
        1
        for candidate in first
        if set(canonical_payload(candidate.action_type, candidate.payload))
        != set(expectations["payload_fields"][str(candidate.action_type)])
    )
    fingerprints = [candidate.origin_fingerprint for candidate in first]
    metrics.origin_violations = sum(1 for fingerprint in fingerprints if len(fingerprint) != 64) + (
        len(fingerprints) - len(set(fingerprints))
    )
    metrics.expiry_violations = sum(1 for candidate in first if candidate.expires_at <= reference)
    banned_refs = set(expectations["must_not_appear_refs"])
    metrics.unsafe_refs = sum(1 for candidate in first if banned_refs & set(candidate.source_refs))
    combined_text = " ".join(
        f"{candidate.rationale} {json.dumps(candidate.payload.model_dump(mode='json'))}"
        for candidate in first
    ).lower()
    metrics.unsafe_text = sum(
        1 for text in expectations["must_not_appear_text"] if text in combined_text
    )
    metrics.usefulness_violations = sum(
        1
        for candidate in first
        if not candidate.rationale.strip()
        or candidate.confidence < expectations["minimum_confidence"]
        or any(
            value == "" or value == []
            for value in candidate.payload.model_dump(mode="json").values()
        )
    )
    bindings = [
        approval_binding_hash(candidate.action_type, candidate.payload, 1) for candidate in first
    ]
    metrics.approval_binding_ok = len(set(bindings)) == len(first) and all(
        binding != approval_binding_hash(candidate.action_type, candidate.payload, 2)
        and len(action_payload_hash(candidate.action_type, candidate.payload)) == 64
        for binding, candidate in zip(bindings, first, strict=True)
    )
    return metrics


def render_actions(metrics: ActionMetrics) -> str:
    verdict = "FAIL" if metrics.failed else "PASS"
    lines = [
        f"# Action-proposal eval results — mode `actions` (golden v1, dataset v1) — {verdict}",
        "",
        "Development-set results (ADR 0002): regression floors, not generalisation claims.",
        "",
        "| Check | Value |",
        "|---|---|",
        f"| Proposals composed | {metrics.total_proposals} |",
        f"| Expected action types and evidence refs | {metrics.expected_shape_ok} |",
        f"| Deterministic under repeat composition | {metrics.determinism_ok} |",
        f"| Grounding violations | {metrics.grounding_violations} |",
        f"| Exact typed-payload schema violations | {metrics.payload_schema_violations} |",
        f"| Origin fingerprint uniqueness/shape violations | {metrics.origin_violations} |",
        f"| Invalid or already-expired proposals | {metrics.expiry_violations} |",
        f"| Injection evidence leaked into proposals | {metrics.unsafe_refs} |",
        f"| Injection text leaked into proposals | {metrics.unsafe_text} |",
        f"| Usefulness violations | {metrics.usefulness_violations} |",
        f"| Approval bindings differ by payload/type/version | {metrics.approval_binding_ok} |",
    ]
    return "\n".join(lines)


def render(metrics: Metrics) -> str:
    lines = [
        f"# Eval results — mode `{metrics.mode}` (golden v1, dataset v1)",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Actionable precision | {metrics.precision:.2f} ({metrics.tp} TP / {metrics.fp} FP) |",
        f"| Actionable recall | {metrics.recall:.2f} ({metrics.fn} misses) |",
        f"| Deadline extraction accuracy | {metrics.deadline_correct}/{metrics.deadline_checked} |",
        f"| Duplicate rate | {metrics.duplicates}/{metrics.total_predicted + metrics.duplicates} |",
        f"| Priority-band agreement | {metrics.band_agreed}/{metrics.band_checked} |",
        f"| Unsafe outputs (injection case) | {metrics.unsafe} |",
        f"| Unsupported claims rejected by validation | {metrics.unsupported_rejected} |",
        f"| Confidence-calibration violations | {metrics.calibration_violations} |",
        f"| Signals added by LLM pass | {metrics.llm_added} |",
        f"| Total signals | {metrics.total_predicted} |",
    ]
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["det", "det+mock", "det+anthropic", "brief", "brief+mock", "actions"],
        default="det",
    )
    args = parser.parse_args()
    if args.mode == "actions":
        action_metrics = await run_action_mode()
        report = render_actions(action_metrics)
        exit_code = 1 if action_metrics.failed else 0
    elif args.mode.startswith("brief"):
        brief_metrics = await run_brief_mode(args.mode)
        report = render_brief(brief_metrics)
        exit_code = 1 if brief_metrics.failed else 0
    else:
        metrics = await run_mode(args.mode)
        report = render(metrics)
        exit_code = 1 if metrics.failed else 0
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{args.mode.replace('+', '-')}.md"
    out.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nWritten to {out}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
