"""Phase 2 unit tests: credential crypto + adapters (mock, REST SSRF guard)."""

from __future__ import annotations

import asyncio

import pytest

from app.core import crypto
from app.integrations.mock_adapter import MockAdapter
from app.integrations.registry import get_adapter


def test_encrypt_decrypt_roundtrip():
    token = crypto.encrypt_json({"type": "bearer", "value": "secret-value"})
    assert b"secret-value" not in token  # ciphertext is opaque
    assert crypto.decrypt_json(token) == {"type": "bearer", "value": "secret-value"}


def test_decrypt_with_wrong_key_fails(monkeypatch):
    token = crypto.encrypt_json({"value": "x"})
    monkeypatch.setenv("SECRET_KEY", "a-completely-different-key")
    crypto._fernet.cache_clear() if hasattr(crypto._fernet, "cache_clear") else None
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(crypto.EncryptionError):
        crypto.decrypt_json(token)
    get_settings.cache_clear()


def test_mock_adapter_deterministic_output_and_capabilities():
    adapter = MockAdapter(
        config={"output_prefix": "A:"},
        capabilities={"exposes_retrieved_docs": True, "exposes_token_usage": True},
    )
    case_input = {"input": "hello world", "relevant_doc_ids": ["doc-1", "doc-2"]}
    r1 = asyncio.run(adapter.invoke(case_input, timeout_s=5))
    r2 = asyncio.run(adapter.invoke(case_input, timeout_s=5))
    assert r1.output == r2.output == "A:hello world"  # deterministic
    assert r1.retrieved_documents is not None
    assert [d.doc_id for d in r1.retrieved_documents] == ["doc-1", "doc-2"]
    assert r1.token_usage == r2.token_usage


def test_mock_adapter_hides_unexposed_fields():
    adapter = MockAdapter(config={}, capabilities=None)
    resp = asyncio.run(adapter.invoke({"input": "q"}, timeout_s=5))
    assert resp.retrieved_documents is None  # capability off -> None, not fabricated
    assert resp.agent_trace is None
    assert resp.token_usage is None


def test_mock_adapter_error_triggers():
    adapter = MockAdapter(config={}, capabilities=None)
    with pytest.raises(RuntimeError):
        asyncio.run(adapter.invoke({"input": "please trigger_error now"}, timeout_s=5))


def test_registry_unknown_type_raises():
    with pytest.raises(ValueError):
        get_adapter("nonexistent", {})


def test_rest_adapter_rejects_private_targets():
    from app.core.security import URLValidationError
    from app.integrations.rest_adapter import RestAdapter

    for url in [
        "http://127.0.0.1:8000/api",
        "http://localhost:8080",
        "http://169.254.169.254/latest",
        "http://[::1]/x",
        "http://10.0.0.5/v1",
        "ftp://example.com",
    ]:
        with pytest.raises((URLValidationError, ValueError)):
            RestAdapter(base_url=url)
