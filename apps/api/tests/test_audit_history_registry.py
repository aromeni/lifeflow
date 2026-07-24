"""Stage 9 Delivery Phase 3 closed presentation registry (ADR 0005 D75)."""

from lifeflow_api.audit_history_registry import AUDIT_EVENT_PRESENTATIONS


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
