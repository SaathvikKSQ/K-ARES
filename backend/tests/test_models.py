"""Tests for app settings and the models package wiring."""

from __future__ import annotations

from app.core.config import Settings
from app.db.base import Base
from app.models import (  # noqa: F401
    Application,
    Artifact,
    Dataset,
    DatasetVersion,
    EvaluationRun,
    MetricResult,
    RunEvent,
    TestCase,
    TestResult,
    User,
)


def test_settings_defaults_are_safe_for_dev() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert settings.access_token_expire_minutes > 0


def test_all_tables_registered() -> None:
    expected = {
        "users",
        "applications",
        "application_configs",
        "datasets",
        "dataset_versions",
        "test_cases",
        "evaluation_runs",
        "test_results",
        "metric_results",
        "run_events",
        "artifacts",
    }
    assert expected.issubset(set(Base.metadata.tables))
