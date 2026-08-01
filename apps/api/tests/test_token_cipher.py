import base64
import os

import pytest

from lifeflow_api.security.token_cipher import (
    AesGcmTokenCipher,
    TokenCipherError,
    TokenKeyRing,
    build_key_ring,
    peek_key_id,
)

CTX = "context-a"


def make_cipher(key_id: str = "test-1") -> AesGcmTokenCipher:
    return AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), key_id)


def _random_key_b64() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def test_round_trip() -> None:
    cipher = make_cipher()
    envelope = cipher.encrypt("ya29.a0AfH6-secret", context=CTX)
    assert cipher.decrypt(envelope, context=CTX) == "ya29.a0AfH6-secret"


def test_envelope_never_contains_plaintext() -> None:
    cipher = make_cipher()
    envelope = cipher.encrypt("super-secret-token", context=CTX)
    assert "super-secret-token" not in envelope
    # Stage 11A Phase 4A: every new encryption produces a v2, context-bound
    # envelope — the v1 shape is retained only for reading already-stored data.
    assert envelope.startswith("v2:test-1:")


def test_same_plaintext_gives_different_ciphertexts() -> None:
    cipher = make_cipher()
    assert cipher.encrypt("token", context=CTX) != cipher.encrypt("token", context=CTX)


def test_tampered_envelope_is_rejected() -> None:
    cipher = make_cipher()
    envelope = cipher.encrypt("token", context=CTX)
    head, _, tail = envelope.rpartition(":")
    flipped = base64.b64encode(bytes(b ^ 0x01 for b in base64.b64decode(tail))).decode()
    with pytest.raises(TokenCipherError):
        cipher.decrypt(f"{head}:{flipped}", context=CTX)


def test_wrong_key_fails() -> None:
    envelope = make_cipher().encrypt("token", context=CTX)
    with pytest.raises(TokenCipherError):
        make_cipher().decrypt(envelope, context=CTX)  # same key id, different key material


def test_unknown_key_id_is_rejected() -> None:
    cipher = make_cipher("test-1")
    envelope = cipher.encrypt("token", context=CTX).replace("test-1", "other-key", 1)
    with pytest.raises(TokenCipherError, match="other-key"):
        cipher.decrypt(envelope, context=CTX)


def test_malformed_envelope_is_rejected() -> None:
    with pytest.raises(TokenCipherError):
        make_cipher().decrypt("not-an-envelope", context=CTX)


@pytest.mark.parametrize("bad_key", ["", "shortkey", base64.b64encode(b"x" * 16).decode()])
def test_invalid_keys_are_rejected(bad_key: str) -> None:
    with pytest.raises(TokenCipherError):
        AesGcmTokenCipher(bad_key, "test-1")


# --- Stage 11A Phase 4A: context (AAD) binding -------------------------------


def test_wrong_context_fails_authentication() -> None:
    """S11A-P4A-004/005/006/007: a v2 envelope decrypted with any context
    other than the one it was encrypted with must fail — this is the direct
    proof that an envelope cannot be transplanted across accounts, owners,
    providers, or fields (closing F-P3-03's cross-account gap)."""
    cipher = make_cipher()
    envelope = cipher.encrypt("token", context="account-a:user-a:google:access_token")
    with pytest.raises(TokenCipherError):
        cipher.decrypt(envelope, context="account-b:user-a:google:access_token")  # wrong account
    with pytest.raises(TokenCipherError):
        cipher.decrypt(envelope, context="account-a:user-b:google:access_token")  # wrong owner
    with pytest.raises(TokenCipherError):
        cipher.decrypt(envelope, context="account-a:user-a:calendar:access_token")  # wrong provider
    with pytest.raises(TokenCipherError):
        cipher.decrypt(envelope, context="account-a:user-a:google:refresh_token")  # wrong field


def test_correct_context_round_trips() -> None:
    cipher = make_cipher()
    context = "account-a:user-a:google:access_token"
    envelope = cipher.encrypt("token", context=context)
    assert cipher.decrypt(envelope, context=context) == "token"


def test_v1_envelope_decrypts_regardless_of_context() -> None:
    """S11A-P4A-008: a genuine v1-format envelope — hand-built with no AAD,
    exactly as any row encrypted before Phase 4A would be — must remain
    decryptable, and the `context` argument is accepted but ignored for it,
    since v1 never carried AAD. Not a security regression: v1 never made a
    binding promise `decrypt()` could now break."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw_key = os.urandom(32)
    cipher = AesGcmTokenCipher(base64.b64encode(raw_key).decode(), "v1-test")
    aesgcm = AESGCM(raw_key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, b"legacy-plaintext", None)  # no AAD, matching real v1 data
    v1_envelope = ":".join(
        ("v1", "v1-test", base64.b64encode(nonce).decode(), base64.b64encode(ciphertext).decode())
    )
    assert cipher.decrypt(v1_envelope, context="anything-at-all") == "legacy-plaintext"
    assert cipher.decrypt(v1_envelope, context="something-else-entirely") == "legacy-plaintext"


def test_peek_key_id_does_not_require_decryption() -> None:
    cipher = make_cipher("peekable-1")
    envelope = cipher.encrypt("token", context=CTX)
    assert peek_key_id(envelope) == "peekable-1"


def test_peek_key_id_rejects_malformed_envelope() -> None:
    with pytest.raises(TokenCipherError):
        peek_key_id("not-an-envelope")


# --- Stage 11A Phase 4A: TokenKeyRing ----------------------------------------


def test_key_ring_encrypts_with_the_active_key() -> None:
    active = make_cipher("active-1")
    legacy = make_cipher("legacy-1")
    ring = TokenKeyRing(active, [legacy])
    envelope = ring.encrypt("token", context=CTX)
    assert peek_key_id(envelope) == "active-1"


def test_key_ring_decrypts_a_legacy_key_row() -> None:
    active = make_cipher("active-1")
    legacy = make_cipher("legacy-1")
    ring = TokenKeyRing(active, [legacy])
    old_envelope = legacy.encrypt("legacy-token", context=CTX)
    assert ring.decrypt(old_envelope, context=CTX) == "legacy-token"


def test_key_ring_rejects_unknown_key_id() -> None:
    active = make_cipher("active-1")
    ring = TokenKeyRing(active)
    other = make_cipher("stranger-1")
    envelope = other.encrypt("token", context=CTX)
    with pytest.raises(TokenCipherError, match="stranger-1"):
        ring.decrypt(envelope, context=CTX)


def test_key_ring_rejects_duplicate_key_ids() -> None:
    active = make_cipher("shared-id")
    legacy = make_cipher("shared-id")
    with pytest.raises(TokenCipherError, match="uplicate"):
        TokenKeyRing(active, [legacy])


def test_key_ring_needs_rotation() -> None:
    active = make_cipher("active-1")
    ring = TokenKeyRing(active, [make_cipher("legacy-1")])
    assert ring.needs_rotation("legacy-1") is True
    assert ring.needs_rotation("active-1") is False


# --- Stage 11A Phase 4A: build_key_ring configuration validation -------------


def test_build_key_ring_with_no_legacy_keys() -> None:
    ring = build_key_ring(_random_key_b64(), "active-1", "")
    assert ring.active_key_id == "active-1"
    assert ring.legacy_key_ids == frozenset()


def test_build_key_ring_with_legacy_keys() -> None:
    import json

    legacy_json = json.dumps([{"key": _random_key_b64(), "key_id": "legacy-1"}])
    ring = build_key_ring(_random_key_b64(), "active-1", legacy_json)
    assert ring.legacy_key_ids == frozenset({"legacy-1"})


def test_build_key_ring_rejects_malformed_json() -> None:
    with pytest.raises(TokenCipherError, match="not valid JSON"):
        build_key_ring(_random_key_b64(), "active-1", "{not json")


def test_build_key_ring_rejects_non_array_json() -> None:
    with pytest.raises(TokenCipherError, match="must be a JSON array"):
        build_key_ring(_random_key_b64(), "active-1", "{}")


def test_build_key_ring_rejects_malformed_entry_shape() -> None:
    with pytest.raises(TokenCipherError):
        build_key_ring(_random_key_b64(), "active-1", '[{"key": "abc"}]')


def test_build_key_ring_rejects_duplicate_active_and_legacy_ids() -> None:
    import json

    legacy_json = json.dumps([{"key": _random_key_b64(), "key_id": "active-1"}])
    with pytest.raises(TokenCipherError, match="uplicate"):
        build_key_ring(_random_key_b64(), "active-1", legacy_json)


def test_build_key_ring_rejects_invalid_legacy_key_material() -> None:
    import json

    legacy_json = json.dumps([{"key": "not-base64!!", "key_id": "legacy-1"}])
    with pytest.raises(TokenCipherError):
        build_key_ring(_random_key_b64(), "active-1", legacy_json)
