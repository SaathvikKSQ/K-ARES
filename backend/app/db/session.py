"""Engine and session factory.

PostgreSQL in production; SQLite for tests/dev (``check_same_thread`` disabled
because FastAPI sync endpoints run in a thread pool).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def _engine_kwargs(url: str, settings: Settings) -> dict[str, Any]:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": True,
    }


def create_db_engine(settings: Settings | None = None) -> Engine:
    """Create a configured SQLAlchemy engine for the settings' database URL."""
    settings = settings or get_settings()
    engine = create_engine(settings.database_url, echo=settings.db_echo, future=True)
    if settings.database_url.startswith("sqlite"):
        # Enforce FK integrity (off by default in SQLite).
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection: Any, _record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the process-wide engine (created lazily)."""
    global _engine, _factory
    if _engine is None:
        _engine = create_db_engine()
        _factory = make_session_factory(_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory (created lazily)."""
    get_engine()
    assert _factory is not None
    return _factory


def reset_engine() -> None:
    """Dispose and forget the cached engine (used by tests)."""
    global _engine, _factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
