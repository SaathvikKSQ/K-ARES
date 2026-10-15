"""SQLAlchemy models. Importing this package registers all tables on Base."""

from app.models.application import Application, ApplicationConfig
from app.models.artifact import Artifact
from app.models.dataset import Dataset, DatasetVersion, TestCase
from app.models.evaluation import EvaluationRun, RunEvent
from app.models.results import MetricResult, TestResult
from app.models.user import User

__all__ = [
    "Application",
    "ApplicationConfig",
    "Artifact",
    "Dataset",
    "DatasetVersion",
    "EvaluationRun",
    "MetricResult",
    "RunEvent",
    "TestCase",
    "TestResult",
    "User",
]
