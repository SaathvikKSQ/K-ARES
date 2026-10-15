"""Seed script: creates the initial admin user from environment settings.

Run: ``python -m app.db.seed`` (after ``alembic upgrade head``).
Never logs the password (SR-10).
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_session_factory
from app.services.user_service import seed_admin_from_env

logger = logging.getLogger(__name__)


def main() -> int:
    """Seed the initial admin user; returns a process exit code."""
    settings = get_settings()
    configure_logging(settings.log_level)
    session = get_session_factory()()
    try:
        status = seed_admin_from_env(session, settings)
        session.commit()
        logger.info("Seed result: %s", status)
        return 0
    except Exception:
        session.rollback()
        logger.exception("Seeding failed")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
