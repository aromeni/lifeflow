"""Stage 9 Delivery Phase 3 closed presentation registry (ADR 0005 D75, D79)."""

from lifeflow_api.audit_history_registry import (
    AUDIT_EVENT_PRESENTATIONS,
    safe_action_type_label,
    safe_counts,
    safe_reason_label,
)


def test_presentation_registry_is_closed_and_fixed() -> None:
    assert len(AUDIT_EVENT_PRESENTATIONS) == len(set(AUDIT_EVENT_PRESENTATIONS))
    assert all("." in event_type for event_type in AUDIT_EVENT_PRESENTATIONS)
    assert all(view.title and view.summary for view in AUDIT_EVENT_PRESENTATIONS.values())
    rendered = " ".join(
        f"{view.title} {view.summary}" for view in AUDIT_EVENT_PRESENTATIONS.values()
    )
    assert "{" not in rendered
    assert "metadata" not in rendered.lower()


def test_retention_cancelled_operation_is_registered() -> None:
    """Regression pin: `cancel_operation` (Phase 2) accepts any owner-scoped
    operation in pending/previewed state regardless of type, and retention
    operations are created directly in `pending`, so a cancelled retention
    operation is a reachable event. It must stay registered rather than
    silently disappearing from history."""
    assert "retention.operation_cancelled" in AUDIT_EVENT_PRESENTATIONS


def test_uncertain_execution_states_no_automatic_retry() -> None:
    presentation = AUDIT_EVENT_PRESENTATIONS["execution.uncertain"]
    assert "did not retry automatically" in presentation.summary


def test_safe_action_type_label_is_a_closed_lookup() -> None:
    assert safe_action_type_label("create_task") == "Task"
    assert safe_action_type_label("create_gmail_draft") == "Gmail draft"
    assert safe_action_type_label("create_calendar_event") == "Calendar event"
    # Unknown, malformed, or non-string values are omitted, never echoed back.
    assert safe_action_type_label("SENTINEL-UNKNOWN-ACTION-TYPE") is None
    assert safe_action_type_label(None) is None
    assert safe_action_type_label(42) is None
    assert safe_action_type_label(["create_task"]) is None


def test_safe_reason_label_is_a_closed_lookup() -> None:
    assert safe_reason_label("proposal_expired") == "The proposal had expired"
    assert safe_reason_label("provider_revoke_failed") == "Provider access could not be revoked"
    # The one parametrized code is matched structurally, bounded to 4xx/5xx.
    assert safe_reason_label("google_client_error_503") is not None
    assert safe_reason_label("google_client_error_999") is None
    assert safe_reason_label("google_client_error_abc") is None
    # Unknown, malformed, or non-string values are omitted, never echoed back.
    assert safe_reason_label("SENTINEL-UNKNOWN-REASON") is None
    assert safe_reason_label(None) is None
    assert safe_reason_label(123) is None


def test_safe_counts_extracts_only_the_three_approved_keys() -> None:
    assert safe_counts({"deleted_count": 36, "preserved_count": 1}) == {
        "deleted_count": 36,
        "preserved_count": 1,
    }
    assert safe_counts({"failed_count": 0}) == {"failed_count": 0}
    # Unknown keys, arbitrary structures, and non-dict input are all ignored.
    assert safe_counts({"deleted_count": 5, "record_id": "x", "scope": {}}) == {"deleted_count": 5}
    assert safe_counts({}) == {}
    assert safe_counts(None) == {}
    assert safe_counts("not-a-dict") == {}


def test_safe_counts_rejects_malformed_values() -> None:
    assert safe_counts({"deleted_count": -1}) == {}
    assert safe_counts({"deleted_count": True}) == {}
    assert safe_counts({"deleted_count": "36"}) == {}
    assert safe_counts({"deleted_count": 3.5}) == {}
    assert safe_counts({"deleted_count": 1_000_001}) == {}
    assert safe_counts({"deleted_count": 1_000_000}) == {"deleted_count": 1_000_000}


def test_typed_detail_labels_never_echo_a_raw_code_or_mention_metadata() -> None:
    """The closed registry principle applies to the typed-detail labels too:
    no label is allowed to be, or contain, the raw wire-format code it stands
    for, and none may reference "metadata"."""
    from lifeflow_api.audit_history_registry import (
        _SAFE_ACTION_TYPE_LABELS,
        _SAFE_REASON_LABELS,
    )

    for raw_code, label in {**_SAFE_ACTION_TYPE_LABELS, **_SAFE_REASON_LABELS}.items():
        assert raw_code != label
        assert "metadata" not in label.lower()
