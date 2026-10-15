"""Pydantic API schemas (Phase 1: common envelope, auth, health)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Standard pagination envelope."""

    items: list[T]
    page: int = 1
    page_size: int = 25
    total: int = 0


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: str
    is_active: bool


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str
    environment: str


class ErrorDetail(BaseModel):
    field: str | None = None
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = []


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    request_id: str


class TimestampModel(BaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None
