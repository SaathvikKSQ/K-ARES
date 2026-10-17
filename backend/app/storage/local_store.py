"""Local filesystem artifact store (SR-12..SR-14).

Files live under ``DATA_DIR``; keys are content-addressed (sha256) so identical
uploads dedupe naturally. Size limits are enforced by callers before writing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from app.core.config import get_settings

MAX_FILE_BYTES = 10 * 1024 * 1024  # hard server-side cap (mirrors max_upload_mb)


class StorageError(ValueError):
    """Raised on size violations or IO failures."""


def _base_dir() -> Path:
    path = Path(get_settings().data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_key(key: str) -> Path:
    """Reject path traversal; keys are sha256 hex + '/' + filename."""
    resolved = (_base_dir() / key).resolve()
    if not str(resolved).startswith(str(_base_dir().resolve())):
        raise StorageError("invalid storage key")
    if resolved.is_dir():
        raise StorageError("invalid storage key")
    return resolved


def store_bytes(content: bytes, subdir: str = "datasets") -> tuple[str, str]:
    """Write content under a content-addressed key. Returns (key, sha256)."""
    if len(content) > MAX_FILE_BYTES:
        raise StorageError(f"file exceeds maximum size of {MAX_FILE_BYTES} bytes")
    digest = hashlib.sha256(content).hexdigest()
    key = f"{subdir}/{digest[:2]}/{digest}.bin"
    path = _safe_key(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():  # content-addressed: skip rewrite on dedupe
        path.write_bytes(content)
    return key, digest


def read_bytes(key: str) -> bytes:
    path = _safe_key(key)
    if not path.exists():
        raise StorageError("file not found in storage")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise StorageError("stored file exceeds maximum size")
    return path.read_bytes()


def delete_file(key: str) -> bool:
    path = _safe_key(key)
    if path.exists():
        path.unlink()
        return True
    return False
