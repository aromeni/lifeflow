"""The single, shared definition of a credential's AAD context string.

Every caller that encrypts or decrypts a `ConnectedAccount` token field
(`accounts.py`, `google_wiring.py`, `credential_rotation.py`) must derive the
context identically, or a legitimate row would fail its own authentication
check. Keeping the format in exactly one place (Stage 11A Phase 4A) makes
that guarantee structural rather than a convention callers could drift from.
"""

import uuid

ACCESS_TOKEN_FIELD = "access_token"  # noqa: S105 — a field *name*, not a secret
REFRESH_TOKEN_FIELD = "refresh_token"  # noqa: S105 — a field *name*, not a secret


def credential_context(
    *, connected_account_id: uuid.UUID, user_id: uuid.UUID, provider: str, field: str
) -> str:
    """The AAD bound into a `v2` credential envelope.

    Binding the account id, owner id, provider, and field name means an
    envelope copied into a different row's column — a different account, a
    different owner, or the sibling token field of the same row — fails
    AES-GCM authentication instead of silently decrypting (closes the
    cross-account/cross-field gap identified in F-P3-03's remediation).
    """
    return f"{connected_account_id}:{user_id}:{provider}:{field}"
