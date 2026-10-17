"""Application API schemas. Secrets are write-only (SR-8): never serialized."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ApplicationType, IntegrationType


class CapabilityFlags(BaseModel):
    exposes_retrieved_docs: bool = False
    exposes_citations: bool = False
    exposes_traces: bool = False
    exposes_token_usage: bool = False
    streaming: bool = False


class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    application_type: ApplicationType
    integration_type: IntegrationType
    base_url: str | None = Field(default=None, max_length=2048)
    invoke_path: str = ""
    # Write-only credentials: accepted on input, never returned.
    credentials: dict[str, Any] | None = Field(default=None, exclude=True)
    capabilities: CapabilityFlags = Field(default_factory=CapabilityFlags)
    version_label: str | None = Field(default=None, max_length=120)
    model_name: str | None = Field(default=None, max_length=200)
    prompt_version: str | None = Field(default=None, max_length=120)
    code_revision: str | None = Field(default=None, max_length=120)
    owner: str | None = Field(default=None, max_length=120)

    @field_validator("credentials")
    @classmethod
    def _credential_keys_allowed(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return None
        allowed = {"type", "value", "header", "username", "password"}
        unknown = set(v) - allowed
        if unknown:
            raise ValueError(f"unsupported credential fields: {sorted(unknown)}")
        return v


class ApplicationUpdate(BaseModel):
    description: str | None = None
    base_url: str | None = Field(default=None, max_length=2048)
    invoke_path: str | None = None
    credentials: dict[str, Any] | None = Field(default=None, exclude=True)
    capabilities: CapabilityFlags | None = None
    is_enabled: bool | None = None
    version_label: str | None = Field(default=None, max_length=120)
    model_name: str | None = Field(default=None, max_length=200)
    prompt_version: str | None = Field(default=None, max_length=120)
    code_revision: str | None = Field(default=None, max_length=120)
    owner: str | None = Field(default=None, max_length=120)

    @field_validator("credentials")
    @classmethod
    def _credential_keys_allowed(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return None
        allowed = {"type", "value", "header", "username", "password"}
        unknown = set(v) - allowed
        if unknown:
            raise ValueError(f"unsupported credential fields: {sorted(unknown)}")
        return v


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    application_type: ApplicationType
    integration_type: IntegrationType
    base_url: str | None = None
    invoke_path: str = ""
    has_credentials: bool = False
    capabilities: CapabilityFlags
    current_version_label: str | None = None
    is_enabled: bool
    owner: str | None = None
    last_connection_test: dict[str, Any] | None = None


class ConnectionTestRequest(BaseModel):
    base_url: str | None = Field(default=None, max_length=2048)
    credentials: dict[str, Any] | None = Field(default=None, exclude=True)


class ConnectionTestOut(BaseModel):
    success: bool
    message: str
    latency_ms: int | None = None
