"""Background worker: claims queued runs and executes them (T3.4, FR-C).

A single daemon thread polls the DB for ``queued`` runs and executes each via
``run_service.execute_run`` (which drives the engine with DB-backed ports).
Claiming is guarded by a conditional UPDATE so concurrent workers cannot
double-execute the same run. Enabled by ``RUN_WORKER_ENABLED`` (tests disable
it for determinism and drive the engine directly).
"""

from __future__ import annotations

import logging
import threading

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RunWorker:
    """Polls for queued runs and executes them, one at a time."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="kaers-run-worker", daemon=True
        )
        self._thread.start()
        logger.info("Run worker started")

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        logger.info("Run worker stopped")

    def _loop(self) -> None:
        settings = get_settings()
        while not self._stop_event.is_set():
            try:
                from app.db.session import get_session_factory
                from app.services import run_service

                session = get_session_factory()()
                try:
                    claimed = run_service.claim_next_queued_run(session)
                finally:
                    session.close()
                if claimed is None:
                    self._stop_event.wait(settings.run_poll_interval_s)
                else:
                    run_service.execute_run(claimed)
            except Exception:
                logger.exception("Run worker iteration failed")
                self._stop_event.wait(1.0)


_worker = RunWorker()


def start_worker() -> None:
    """Start the worker if enabled (called from app lifespan)."""
    if get_settings().run_worker_enabled:
        _worker.start()


def stop_worker() -> None:
    """Stop the worker (called from app lifespan shutdown)."""
    _worker.stop()
