"""Application-level encryption for OAuth tokens (threat model T1, ADR 0001 D7).

Tokens are encrypted before they reach the database. The ciphertext envelope
carries a key id so keys can be rotated (decrypt with the old key, re-encrypt
with the new) and so a managed-KMS implementation can replace this one in
production without changing callers.

Envelope formats:
  v1:<key_id>:<base64 nonce>:<base64 ciphertext>   (legacy, no AAD)
  v2:<key_id>:<base64 nonce>:<base64 ciphertext>   (AAD-bound, Stage 11A Phase 4A)

`v1` envelopes were encrypted with no associated authenticated data (AAD) and
remain decryptable unchanged — `context` is accepted but ignored for `v1` so
already-encrypted synthetic records never need an emergency migration. Every
new encryption always produces a `v2` envelope, whose AES-GCM authentication
tag is bound to a caller-supplied `context` string (see `credential_rotation.py`
and `accounts.py` for the `<account_id>:<user_id>:<provider>:<field>` context
this application uses) so a ciphertext copied into a different row's column,
or the sibling field of the same row, fails authentication instead of quietly
decrypting (Stage 11A Phase 4A, closing F-P3-03's cross-account gap).

`TokenKeyRing` holds one active key (used for every new encryption) plus zero
or more legacy keys (retained only long enough to decrypt not-yet-migrated
rows) and implements the same `TokenCipher` protocol as a single
`AesGcmTokenCipher`, so it is a drop-in replacement for every existing caller.
"""

import base64
import json
import os
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_ENVELOPE_VERSION_V1 = "v1"
_ENVELOPE_VERSION_V2 = "v2"
_NONCE_BYTES = 12  # AES-GCM standard nonce size


class TokenCipherError(Exception):
    """Encryption or decryption failed. Never contains key or token material."""


class TokenCipher(Protocol):
    def encrypt(self, plaintext: str, *, context: str) -> str: ...
    def decrypt(self, envelope: str, *, context: str) -> str: ...


def peek_key_id(envelope: str) -> str:
    """Return the key id recorded in an envelope, without decrypting it.

    Used by the rotation service to decide which cipher in a key ring should
    handle a given row, and to backfill the `*_key_id` database columns from
    already-encrypted envelopes without needing any key material.
    """
    parts = envelope.split(":")
    if len(parts) != 4 or parts[0] not in (_ENVELOPE_VERSION_V1, _ENVELOPE_VERSION_V2):
        raise TokenCipherError("Unrecognised token envelope format.")
    return parts[1]


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

    def encrypt(self, plaintext: str, *, context: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode(), context.encode())
        return ":".join(
            (
                _ENVELOPE_VERSION_V2,
                self._key_id,
                base64.b64encode(nonce).decode(),
                base64.b64encode(ciphertext).decode(),
            )
        )

    def decrypt(self, envelope: str, *, context: str) -> str:
        parts = envelope.split(":")
        if len(parts) != 4 or parts[0] not in (_ENVELOPE_VERSION_V1, _ENVELOPE_VERSION_V2):
            raise TokenCipherError("Unrecognised token envelope format.")
        version, key_id, nonce_b64, ciphertext_b64 = parts
        if key_id != self._key_id:
            raise TokenCipherError(f"No key available for key id '{key_id}'.")
        aad = context.encode() if version == _ENVELOPE_VERSION_V2 else None
        try:
            nonce = base64.b64decode(nonce_b64, validate=True)
            ciphertext = base64.b64decode(ciphertext_b64, validate=True)
            return self._aesgcm.decrypt(nonce, ciphertext, aad).decode()
        except InvalidTag as exc:
            raise TokenCipherError("Token decryption failed (wrong key or tampering).") from exc
        except TokenCipherError:
            raise
        except Exception as exc:
            raise TokenCipherError("Token envelope is corrupt.") from exc


class TokenKeyRing:
    """One active cipher plus zero or more legacy ciphers, sharing one protocol.

    New encryptions always go through the active key. Decryption dispatches
    to whichever key the envelope names, active or legacy; an envelope naming
    a key this ring does not hold fails with the same "no key available"
    error a single `AesGcmTokenCipher` would raise, so callers never need to
    distinguish "single key" from "key ring" error handling.
    """

    def __init__(
        self, active: AesGcmTokenCipher, legacy: list[AesGcmTokenCipher] | None = None
    ) -> None:
        legacy = legacy or []
        all_ids = [active.key_id, *(cipher.key_id for cipher in legacy)]
        if len(all_ids) != len(set(all_ids)):
            raise TokenCipherError("Duplicate key id across active and legacy keys.")
        self._active = active
        self._legacy_by_id = {cipher.key_id: cipher for cipher in legacy}

    @property
    def active(self) -> AesGcmTokenCipher:
        return self._active

    @property
    def active_key_id(self) -> str:
        return self._active.key_id

    @property
    def legacy_key_ids(self) -> frozenset[str]:
        return frozenset(self._legacy_by_id)

    def encrypt(self, plaintext: str, *, context: str) -> str:
        return self._active.encrypt(plaintext, context=context)

    def decrypt(self, envelope: str, *, context: str) -> str:
        key_id = peek_key_id(envelope)
        cipher = self._resolve(key_id)
        return cipher.decrypt(envelope, context=context)

    def needs_rotation(self, key_id: str) -> bool:
        """True if a row recorded as being on `key_id` is not yet on the active key."""
        return key_id != self._active.key_id

    def _resolve(self, key_id: str) -> AesGcmTokenCipher:
        if key_id == self._active.key_id:
            return self._active
        cipher = self._legacy_by_id.get(key_id)
        if cipher is None:
            raise TokenCipherError(f"No key available for key id '{key_id}'.")
        return cipher


def build_key_ring(active_key_b64: str, active_key_id: str, legacy_json: str) -> TokenKeyRing:
    """Construct the application's one `TokenKeyRing` from raw configuration
    values (Stage 11A Phase 4A). Kept free of any dependency on `config.py`
    so this module stays independently testable; `main.py`/`worker_app.py`
    call this with `settings.token_key`/`token_key_id`/`token_key_legacy_json`.

    `legacy_json`, if non-empty, must be a JSON array of
    `{"key": "<base64>", "key_id": "<id>"}` objects. Every failure mode
    (malformed JSON, wrong shape, invalid key material, a key id duplicated
    against the active key or another legacy entry) raises `TokenCipherError`
    so the caller's existing "construction failed" handling covers this
    without a separate error type.
    """
    active = AesGcmTokenCipher(active_key_b64, active_key_id)
    legacy: list[AesGcmTokenCipher] = []
    if legacy_json.strip():
        try:
            entries = json.loads(legacy_json)
        except json.JSONDecodeError as exc:
            raise TokenCipherError("TOKEN_KEY_LEGACY_JSON is not valid JSON.") from exc
        if not isinstance(entries, list):
            raise TokenCipherError("TOKEN_KEY_LEGACY_JSON must be a JSON array.")
        for entry in entries:
            if not isinstance(entry, dict) or "key" not in entry or "key_id" not in entry:
                raise TokenCipherError(
                    'Each TOKEN_KEY_LEGACY_JSON entry must be {"key": ..., "key_id": ...}.'
                )
            legacy.append(AesGcmTokenCipher(entry["key"], entry["key_id"]))
    return TokenKeyRing(active, legacy)
