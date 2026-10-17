"""Credential encryption at rest (SR-8).

Fernet (AES-128-CBC + HMAC-SHA256) with a key from ``SECRET_ENCRYPTION_KEY``.
If not configured, a key is derived from ``SECRET_KEY`` (development convenience
only; production must set ``SECRET_ENCRYPTION_KEY`` explicitly).
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    key_material = (
        settings.secret_encryption_key or settings.secret_key
    ).encode("utf-8")
    derived = hashlib.sha256(key_material).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


class EncryptionError(ValueError):
    """Raised when decryption fails (wrong key or corrupted payload)."""


def encrypt_json(payload: dict[str, Any]) -> bytes:
    """Encrypt a JSON-serializable dict; returns Fernet token bytes."""
    return _fernet().encrypt(json.dumps(payload, default=str).encode("utf-8"))


def decrypt_json(token: bytes) -> dict[str, Any]:
    """Decrypt a Fernet token back into a dict."""
    try:
        raw = _fernet().decrypt(token)
    except InvalidToken as exc:
        raise EncryptionError("credential payload could not be decrypted") from exc
    return json.loads(raw.decode("utf-8"))


def generate_key() -> str:
    """Generate a new Fernet key (utility for operators)."""
    return Fernet.generate_key().decode("ascii")
