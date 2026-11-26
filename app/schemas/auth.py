"""인증 요청/응답 스키마."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

PASSWORD_MIN_LENGTH = 8
# bcrypt 는 72 byte 이후를 무시하므로 그 이상은 받지 않는다 (한글은 1자 3 byte).
PASSWORD_MAX_BYTES = 72


def normalize_email(email: str) -> str:
    return email.strip().lower()


class Credentials(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class SignupRequest(Credentials):
    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        if len(value) < PASSWORD_MIN_LENGTH:
            raise ValueError(f"비밀번호는 {PASSWORD_MIN_LENGTH}자 이상이어야 합니다.")
        if len(value.encode("utf-8")) > PASSWORD_MAX_BYTES:
            raise ValueError(f"비밀번호가 너무 깁니다 (최대 {PASSWORD_MAX_BYTES} byte).")
        return value


class LoginRequest(Credentials):
    pass


class DeviceRequest(BaseModel):
    # 앱이 처음 켜질 때 만든 무작위 키 (32 byte 이상 권장, base64url/hex).
    device_key: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str | None
    timezone: str
    created_at: datetime
