"""Application-level encryption for OAuth tokens (threat model T1, ADR 0001 D7).

Tokens are encrypted before they reach the database. The ciphertext envelope
carries a key id so keys can be rotated (decrypt with the old key, re-encrypt
with the new) and so a managed-KMS implementation can replace this one in
production without changing callers.

Envelope format:  v1:<key_id>:<base64 nonce>:<base64 ciphertext>
"""

import base64
import os
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ENVELOPE_VERSION = "v1"
_NONCE_BYTES = 12  # AES-GCM standard nonce size


class TokenCipherError(Exception):
    """Encryption or decryption failed. Never contains key or token material."""


class TokenCipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, envelope: str) -> str: ...


class AesGcmTokenCipher:
    """AES-256-GCM cipher with an environment-managed key.

    `key_b64` is a base64-encoded 32-byte key (generate one with
    `python3 -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"`).
    """

    def __init__(self, key_b64: str, key_id: str) -> None:
        try:
            key = base64.b64decode(key_b64, validate=True)
        except Exception as exc:
            raise TokenCipherError("Token key is not valid base64.") from exc
        if len(key) != 32:
            raise TokenCipherError("Token key must decode to exactly 32 bytes.")
        if not key_id or ":" in key_id:
            raise TokenCipherError("Key id must be non-empty and contain no ':'.")
        self._aesgcm = AESGCM(key)
        self._key_id = key_id

    @property
    def key_id(self) -> str:
        return self._key_id

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return ":".join(
            (
                _ENVELOPE_VERSION,
                self._key_id,
                base64.b64encode(nonce).decode(),
                base64.b64encode(ciphertext).decode(),
            )
        )

    def decrypt(self, envelope: str) -> str:
        parts = envelope.split(":")
        if len(parts) != 4 or parts[0] != _ENVELOPE_VERSION:
            raise TokenCipherError("Unrecognised token envelope format.")
        _, key_id, nonce_b64, ciphertext_b64 = parts
        if key_id != self._key_id:
            raise TokenCipherError(f"No key available for key id '{key_id}'.")
        try:
            nonce = base64.b64decode(nonce_b64, validate=True)
            ciphertext = base64.b64decode(ciphertext_b64, validate=True)
            return self._aesgcm.decrypt(nonce, ciphertext, None).decode()
        except InvalidTag as exc:
            raise TokenCipherError("Token decryption failed (wrong key or tampering).") from exc
        except TokenCipherError:
            raise
        except Exception as exc:
            raise TokenCipherError("Token envelope is corrupt.") from exc
