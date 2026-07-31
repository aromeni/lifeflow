"""Stage 11A Phase 2 (docs/delivery/stage-11a-phase-2-plan.md), scenario
S11A-P2-025: storage-exhaustion classification.

Scoping note (see the acceptance matrix's scoping note): LifeFlow's runtime
code writes no application-managed local files — its only durable-storage
boundary is PostgreSQL (Redis is explicitly non-durable, ADR 0004 D48).
A host-disk-full simulation was considered and rejected as exercising a
code path this product does not have. What genuinely exists, and is
verified here, is that a PostgreSQL "no space left on device" condition —
which SQLAlchemy always surfaces as an `OperationalError` regardless of the
underlying OS error — is classified exactly like any other database
outage: retryable, a safe fixed message, and never the raw driver error
text (which could contain a filesystem path or other host detail).
"""

import pytest
from sqlalchemy.exc import OperationalError

from lifeflow_api.failure_taxonomy import FailureCode, Severity, classify_exception, safe_message

pytestmark = pytest.mark.integration


def test_postgres_disk_full_classifies_as_database_unavailable_not_raw_text() -> None:
    # A real asyncpg "no space left on device" error looks like this —
    # constructed directly here rather than actually exhausting a disk,
    # since the classification depends only on the exception type, not on
    # genuinely running out of storage.
    exc = OperationalError(
        "INSERT INTO source_items ...",
        {},
        Exception('could not extend file "base/16389/16401": No space left on device'),
    )

    classification = classify_exception(exc)

    assert classification.code == FailureCode.database_unavailable
    assert classification.retryable is True
    assert classification.severity == Severity.error
    assert classification.safe_message == safe_message(FailureCode.database_unavailable)
    # The raw driver message (which names a real on-disk file path) must
    # never appear in what gets classified back out.
    assert "base/16389" not in classification.safe_message
    assert "No space left on device" not in classification.safe_message
