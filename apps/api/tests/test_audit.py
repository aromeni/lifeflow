import uuid
from unittest.mock import Mock

import pytest

from lifeflow_api.audit import UnsafeAuditMetadataError, record_audit_event
from lifeflow_api.repositories import AuditEventRepository


@pytest.mark.parametrize(
    "bad_key",
    ["access_token", "refreshToken", "client_secret", "PASSWORD", "Authorization", "cookie_jar"],
)
def test_secret_shaped_metadata_keys_are_rejected(bad_key: str) -> None:
    with pytest.raises(UnsafeAuditMetadataError):
        record_audit_event(
            Mock(),
            user_id=uuid.uuid4(),
            actor="system",
            event_type="test.event",
            entity_type="user",
            entity_id="x",
            metadata={bad_key: "value"},
        )


def test_audit_repository_is_append_only() -> None:
    exposed = {name for name in dir(AuditEventRepository) if not name.startswith("_")}
    assert exposed == {"append", "list", "list_for_entity", "list_history_page"}, (
        f"append-only contract violated: {exposed}"
    )
