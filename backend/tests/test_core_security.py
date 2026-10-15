"""Security utility tests: redaction, tokens, passwords, SSRF validation (SR-10, SR-15)."""

from __future__ import annotations

import pytest

from app.core.logging import redact_secrets
from app.core.security import (
    TokenError,
    URLValidationError,
    create_access_token,
    hash_password,
    validate_target_url,
    verify_access_token,
    verify_password,
)

SECRET = "unit-test-secret-key"


def test_redact_secrets_masks_sensitive_keys() -> None:
    data = {
        "api_key": "sk-123",
        "Authorization": "Bearer abc",
        "nested": {"PASSWORD": "hunter2", "safe": "value"},
        "list": [{"auth_token": "t"}],
        "name": "keep",
    }
    redacted = redact_secrets(data)
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["Authorization"] == "***REDACTED***"
    assert redacted["nested"]["PASSWORD"] == "***REDACTED***"
    assert redacted["nested"]["safe"] == "value"
    assert redacted["list"][0]["auth_token"] == "***REDACTED***"
    assert redacted["name"] == "keep"
    # Original untouched
    assert data["api_key"] == "sk-123"


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_token_roundtrip() -> None:
    token = create_access_token("user-1", "admin", SECRET, expires_in_seconds=60)
    claims = verify_access_token(token, SECRET)
    assert claims["sub"] == "user-1"
    assert claims["role"] == "admin"


def test_token_rejects_tampering_and_expiry() -> None:
    token = create_access_token("user-1", "admin", SECRET, expires_in_seconds=60)
    with pytest.raises(TokenError):
        verify_access_token(token, "other-secret")
    expired = create_access_token("user-1", "admin", SECRET, expires_in_seconds=-10)
    with pytest.raises(TokenError, match="expired"):
        verify_access_token(expired, SECRET)
    with pytest.raises(TokenError):
        verify_access_token("not-a-token", SECRET)


def test_validate_target_url_rejects_bad_schemes() -> None:
    for url in ("ftp://example.com", "file:///etc/passwd", "", "example.com"):
        with pytest.raises(URLValidationError):
            validate_target_url(url)


def test_validate_target_url_blocks_private_hosts() -> None:
    with pytest.raises(URLValidationError):
        validate_target_url("http://127.0.0.1:8000")
    with pytest.raises(URLValidationError):
        validate_target_url("http://localhost/api")


def test_validate_target_url_allows_public(monkeypatch) -> None:
    # Avoid real DNS: monkeypatch getaddrinfo to a public address.
    import socket

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 80))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert validate_target_url("https://example.com/api") == "https://example.com/api"


def test_validate_target_url_private_allowed_flag() -> None:
    assert (
        validate_target_url("http://localhost:8000", allow_private_targets=True)
        == "http://localhost:8000"
    )
