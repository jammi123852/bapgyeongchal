"""API 공통 의존성."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="인증이 필요합니다.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Bearer 토큰으로 현재 사용자를 찾는다.

    다음 경우 모두 같은 401 을 반환한다 (어느 조건에 걸렸는지 노출하지 않음):
    토큰 없음 / 서명·만료 오류 / 사용자 없음 / soft delete 된 사용자 / 로그아웃된 토큰.
    """
    if credentials is None:
        raise _UNAUTHORIZED
    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise _UNAUTHORIZED from None

    user = db.get(User, payload.user_id)
    if user is None or user.is_deleted or user.token_version != payload.token_version:
        raise _UNAUTHORIZED
    return user
