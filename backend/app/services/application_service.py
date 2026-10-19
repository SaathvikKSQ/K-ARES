"""Application service: CRUD, credential encryption, connection tests (T2.1/T2.3)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.security import URLValidationError, validate_target_url
from app.integrations.base import ConnectionTestResult
from app.integrations.registry import get_adapter
from app.models.application import Application, ApplicationConfig
from app.models.enums import IntegrationType
from app.schemas.application import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationUpdate,
    CapabilityFlags,
    ConnectionTestOut,
)

REST_AUTH_TYPES = {"api_key", "bearer", "basic"}


class ApplicationError(HTTPException):
    def __init__(self, code_status: int, detail: str):
        super().__init__(status_code=code_status, detail=detail)


def _validate_credentials(integration_type: IntegrationType, creds: dict[str, Any] | None) -> None:
    if creds is None:
        return
    if integration_type == IntegrationType.REST_API:
        ctype = creds.get("type")
        if ctype not in REST_AUTH_TYPES:
            raise ApplicationError(422, "credentials.type must be one of api_key|bearer|basic")
        if creds.get("type") == "api_key" and not creds.get("value"):
            raise ApplicationError(422, "credentials.value is required for api_key auth")
        if creds.get("type") == "basic" and not creds.get("username"):
            raise ApplicationError(422, "credentials.username is required for basic auth")
    # Mock adapters need no credentials, but tolerate them (stored encrypted).


def _snapshot(app: Application) -> dict[str, Any]:
    """Sanitized configuration snapshot (no credentials, ever)."""
    return {
        "integration_type": getattr(app.integration_type, "value", app.integration_type),
        "base_url": app.connection_base_url,
        "invoke_path": app.invoke_path,
        "capabilities": app.capabilities,
        "has_credentials": app.connection_config_encrypted is not None,
        "version_label": app.current_version_label,
    }


def _config_hash(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_out(app: Application) -> ApplicationOut:
    return ApplicationOut(
        id=app.id,
        name=app.name,
        description=app.description,
        application_type=app.application_type,
        integration_type=app.integration_type,
        base_url=app.connection_base_url,
        invoke_path=app.invoke_path,
        has_credentials=app.connection_config_encrypted is not None,
        capabilities=CapabilityFlags(**{**CapabilityFlags().model_dump(), **(app.capabilities or {})}),  # noqa: E501
        current_version_label=app.current_version_label,
        is_enabled=app.is_enabled,
        owner=app.owner,
        last_connection_test=app.last_connection_test,
    )


def list_applications(session: Session, enabled_only: bool = False) -> list[ApplicationOut]:
    stmt = select(Application).order_by(Application.name)
    if enabled_only:
        stmt = stmt.where(Application.is_enabled.is_(True))
    return [to_out(app) for app in session.scalars(stmt)]


def get_application(session: Session, app_id: str) -> Application:
    try:
        pk = uuid.UUID(str(app_id))
    except ValueError as exc:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Application not found") from exc
    app = session.get(Application, pk)
    if app is None:
        raise ApplicationError(status.HTTP_404_NOT_FOUND, "Application not found")
    return app


#__PART2__

def _snapshot_config(session: Session, app: Application) -> None:
    snap = _snapshot(app)
    session.add(
        ApplicationConfig(
            application_id=app.id,
            version_label=app.current_version_label,
            config_hash=_config_hash(snap),
            snapshot=snap,
        )
    )


def create_application(session: Session, payload: ApplicationCreate) -> ApplicationOut:
    if session.scalar(select(Application).where(Application.name == payload.name)):
        raise ApplicationError(
            status.HTTP_409_CONFLICT, "An application with this name already exists"
        )
    if payload.integration_type == IntegrationType.REST_API:
        if not payload.base_url:
            raise ApplicationError(422, "base_url is required for rest_api integrations")
        try:
            validate_target_url(payload.base_url)
        except URLValidationError as exc:
            raise ApplicationError(422, f"base_url rejected: {exc}") from exc
    _validate_credentials(payload.integration_type, payload.credentials)

    app = Application(
        name=payload.name,
        description=payload.description,
        application_type=payload.application_type,
        integration_type=payload.integration_type,
        connection_base_url=payload.base_url,
        invoke_path=payload.invoke_path,
        capabilities=payload.capabilities.model_dump(),
        current_version_label=payload.version_label,
        is_enabled=True,
        owner=payload.owner,
    )
    if payload.credentials:
        app.connection_config_encrypted = crypto.encrypt_json(payload.credentials)
    session.add(app)
    session.flush()
    _snapshot_config(session, app)
    session.commit()
    session.refresh(app)
    return to_out(app)


def update_application(
    session: Session, app_id: str, payload: ApplicationUpdate
) -> ApplicationOut:
    app = get_application(session, app_id)
    data = payload.model_dump(exclude_unset=True, exclude={"credentials"})
    if payload.credentials is not None:
        _validate_credentials(app.integration_type, payload.credentials)
        app.connection_config_encrypted = crypto.encrypt_json(payload.credentials)
    for field, value in data.items():
        if field == "base_url" and value is not None:
            try:
                validate_target_url(value)
            except URLValidationError as exc:
                raise ApplicationError(422, f"base_url rejected: {exc}") from exc
        if field == "base_url":
            app.connection_base_url = value
        else:
            setattr(app, field, value)
    session.flush()
    _snapshot_config(session, app)
    session.commit()
    session.refresh(app)
    return to_out(app)


def delete_application(session: Session, app_id: str) -> None:
    app = get_application(session, app_id)
    session.delete(app)
    session.commit()


def build_adapter_config(
    app: Application, credentials: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Assemble the adapter config; decrypts stored credentials when needed."""
    config: dict[str, Any] = {
        "connection": {"base_url": app.connection_base_url, "invoke_path": app.invoke_path},
        "capabilities": app.capabilities or {},
    }
    if credentials is not None:
        config["_credentials"] = credentials
    elif app.connection_config_encrypted:
        config["_credentials"] = crypto.decrypt_json(app.connection_config_encrypted)
    if app.integration_type == IntegrationType.MOCK:
        config = {
            "adapter_config": {
                **config.get("connection", {}),
                "capabilities": config["capabilities"],
            },
            "capabilities": config["capabilities"],
        }
    return config


async def run_connection_test(
    session: Session,
    app: Application,
    base_url_override: str | None = None,
    credentials_override: dict[str, Any] | None = None,
) -> ConnectionTestOut:
    """Test connectivity via the adapter; persist sanitized result only."""
    target = app
    if base_url_override or credentials_override:
        target = Application(
            name=app.name,
            application_type=app.application_type,
            integration_type=app.integration_type,
            connection_base_url=base_url_override or app.connection_base_url,
            invoke_path=app.invoke_path,
            capabilities=app.capabilities,
        )
        if credentials_override:
            target.connection_config_encrypted = crypto.encrypt_json(credentials_override)
        else:
            target.connection_config_encrypted = app.connection_config_encrypted
    if target.integration_type == IntegrationType.REST_API and not target.connection_base_url:
        raise ApplicationError(422, "base_url is required to test a rest_api integration")

    try:
        config = build_adapter_config(target, credentials_override)
        adapter = get_adapter(target.integration_type.value, config)
        result: ConnectionTestResult = await adapter.test_connection()
    except URLValidationError as exc:
        result = ConnectionTestResult(success=False, message=f"URL rejected: {exc}")
    except crypto.EncryptionError:
        result = ConnectionTestResult(
            success=False, message="Stored credentials could not be decrypted"
        )
    except ValueError as exc:
        raise ApplicationError(422, str(exc)) from exc
    except Exception as exc:  # never leak internals/credentials
        result = ConnectionTestResult(
            success=False, message=f"Connection failed: {type(exc).__name__}"
        )

    sanitized = result.model_dump(mode="json") | {"checked_at": datetime.now(UTC).isoformat()}
    target.last_connection_test = sanitized
    if target.id == app.id:
        session.commit()
    return ConnectionTestOut(**result.model_dump())
