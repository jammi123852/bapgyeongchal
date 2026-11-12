"""비밀번호 해시와 access token.

- 비밀번호: bcrypt. bcrypt 는 72 byte 까지만 사용하므로 입력 단계(schemas.auth)에서 길이를 막는다.
- 토큰: HS256 JWT. payload 의 ver 가 users.token_version 과 다르면 무효 (로그아웃 처리).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

# 존재하지 않는 이메일로 로그인할 때도 같은 시간만큼 해시 검증을 수행해
# 응답 시간 차이로 가입 여부가 드러나는 것을 줄인다.
_DUMMY_HASH = bcrypt.hashpw(b"solosafe-dummy-password", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    target = password_hash if password_hash is not None else _DUMMY_HASH
    matched = bcrypt.checkpw(password.encode("utf-8"), target.encode("utf-8"))
    return matched and password_hash is not None


@dataclass(frozen=True)
class TokenPayload:
    user_id: uuid.UUID
    token_version: int


class InvalidTokenError(Exception):
    """서명·만료·형식 중 하나라도 맞지 않는 토큰."""


def create_access_token(user_id: uuid.UUID, token_version: int) -> tuple[str, int]:
    """(token, 만료까지 남은 초) 를 반환한다."""
    settings = get_settings()
    now = datetime.now(UTC)
    expires_in = settings.access_token_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "ver", "exp"]},
        )
        return TokenPayload(user_id=uuid.UUID(payload["sub"]), token_version=int(payload["ver"]))
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidTokenError from exc
