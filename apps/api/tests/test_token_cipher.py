import base64
import os

import pytest

from lifeflow_api.security.token_cipher import AesGcmTokenCipher, TokenCipherError


def make_cipher(key_id: str = "test-1") -> AesGcmTokenCipher:
    return AesGcmTokenCipher(base64.b64encode(os.urandom(32)).decode(), key_id)


def test_round_trip() -> None:
    cipher = make_cipher()
    assert cipher.decrypt(cipher.encrypt("ya29.a0AfH6-secret")) == "ya29.a0AfH6-secret"


def test_envelope_never_contains_plaintext() -> None:
    cipher = make_cipher()
    envelope = cipher.encrypt("super-secret-token")
    assert "super-secret-token" not in envelope
    assert envelope.startswith("v1:test-1:")


def test_same_plaintext_gives_different_ciphertexts() -> None:
    cipher = make_cipher()
    assert cipher.encrypt("token") != cipher.encrypt("token")  # fresh nonce each time


def test_tampered_envelope_is_rejected() -> None:
    cipher = make_cipher()
    envelope = cipher.encrypt("token")
    head, _, tail = envelope.rpartition(":")
    flipped = base64.b64encode(bytes(b ^ 0x01 for b in base64.b64decode(tail))).decode()
    with pytest.raises(TokenCipherError):
        cipher.decrypt(f"{head}:{flipped}")


def test_wrong_key_fails() -> None:
    envelope = make_cipher().encrypt("token")
    with pytest.raises(TokenCipherError):
        make_cipher().decrypt(envelope)  # same key id, different key material


def test_unknown_key_id_is_rejected() -> None:
    cipher = make_cipher("test-1")
    envelope = cipher.encrypt("token").replace("test-1", "other-key", 1)
    with pytest.raises(TokenCipherError, match="other-key"):
        cipher.decrypt(envelope)


def test_malformed_envelope_is_rejected() -> None:
    with pytest.raises(TokenCipherError):
        make_cipher().decrypt("not-an-envelope")


@pytest.mark.parametrize("bad_key", ["", "shortkey", base64.b64encode(b"x" * 16).decode()])
def test_invalid_keys_are_rejected(bad_key: str) -> None:
    with pytest.raises(TokenCipherError):
        AesGcmTokenCipher(bad_key, "test-1")
