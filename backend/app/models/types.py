"""Shared column types (JSONB on PostgreSQL, portable JSON elsewhere)."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

JSONType = JSON().with_variant(JSONB(), "postgresql")
