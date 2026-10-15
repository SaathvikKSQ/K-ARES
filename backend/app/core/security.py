"""Security primitives: password hashing, signed tokens, URL safety checks.

Spec references: specs/security/security-requirements.md SR-2, SR-8, SR-15.
Tokens are HMAC-SHA256 signed compact strings (stdlib only) carrying
``sub`` (user id), ``role`` and ``exp`` (unix seconds).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import socket
import time
from typing import Any
from urllib.parse import urlparse

import bcrypt

from app.core.logging import get_request_id


class TokenError(ValueError):
    """Raised when a token is invalid or expired."""


# ---------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    """Hash a password with bcrypt (cost 12)."""
    if not password:
        raise ValueError("password must not be empty")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time password verification."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ---------------------------------------------------------------- tokens


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _signature(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    return _b64encode(digest)


def create_access_token(user_id: str, role: str, secret_key: str, expires_in_seconds: int) -> str:
    """Create a signed, expiring access token for ``user_id``."""
    payload = json.dumps(
        {"sub": user_id, "role": role, "exp": int(time.time()) + expires_in_seconds}
    ).encode("utf-8")
    encoded = _b64encode(payload)
    return f"{encoded}.{_signature(secret_key, encoded.encode('ascii'))}"


def verify_access_token(token: str, secret_key: str) -> dict[str, Any]:
    """Verify signature and expiry; return the claims or raise ``TokenError``."""
    try:
        encoded, signature = token.split(".", 1)
    except ValueError as exc:
        raise TokenError("malformed token") from exc
    if not hmac.compare_digest(_signature(secret_key, encoded.encode("ascii")), signature):
        raise TokenError("invalid signature")
    try:
        claims = json.loads(_b64decode(encoded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("malformed token") from exc
    if int(claims.get("exp", 0)) < int(time.time()):
        raise TokenError("token expired")
    if "sub" not in claims or "role" not in claims:
        raise TokenError("incomplete claims")
    return claims


# ---------------------------------------------------------------- SSRF guard

_PRIVATE_NETWORKS = [
    ipaddress.ip_network(net)
    for net in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
        "0.0.0.0/8",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "::/128",
    )
]


class URLValidationError(ValueError):
    """Raised when a user-supplied URL fails SSRF validation."""


def validate_target_url(url: str, *, allow_private_targets: bool = False) -> str:
    """Validate a user-supplied target URL for server-side requests.

    Returns the normalized URL string, or raises ``URLValidationError``.
    Blocks non-http(s) schemes and private/loopback/link-local hosts unless
    ``allow_private_targets`` is explicitly enabled (dev only).
    """
    if not url or not isinstance(url, str):
        raise URLValidationError("url must be a non-empty string")
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise URLValidationError("scheme must be http or https")
    if not parsed.hostname:
        raise URLValidationError("missing hostname")
    if allow_private_targets:
        return url.strip()
    # Resolve all addresses; block if any resolved address is private.
    try:
        infos = socket.getaddrinfo(
            parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
        )
    except socket.gaierror as exc:
        raise URLValidationError("hostname could not be resolved") from exc
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if any(addr in network for network in _PRIVATE_NETWORKS):
            raise URLValidationError("private or loopback targets are not allowed")
    return url.strip()


def sanitize_error_message(message: str, max_len: int = 500) -> str:
    """Strip request ids and truncate raw error text before exposing it."""
    cleaned = " ".join(str(message).split())
    if get_request_id() and get_request_id() != "-":
        cleaned = cleaned.replace(get_request_id(), "[request-id]")
    return cleaned[:max_len]
