"""인증 라우트: 기기 자동 계정 / (앱에서 안 쓰는) 이메일 가입·로그인 / 로그아웃 / 내 정보."""

from __future__ import annotations

import hashlib

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    DeviceRequest,
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(tags=["auth"])


def _issue_token(user: User) -> TokenResponse:
    token, expires_in = create_access_token(user.id, user.token_version)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/auth/device", response_model=TokenResponse)
def device(body: DeviceRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """기기 키로 계정을 찾고, 없으면 만든다. 로그인 화면 없이 앱이 켜질 때 부른다.

    기기 키는 무작위 고엔트로피 값이라 sha256 으로 충분하다 (비밀번호와 달리 추측 불가).
    """
    key_hash = hashlib.sha256(body.device_key.encode("ascii")).hexdigest()
    user = db.scalar(sa.select(User).where(User.device_key_hash == key_hash))
    if user is None:
        user = User(device_key_hash=key_hash)
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            # 같은 키로 동시에 두 번 들어온 경우: 먼저 만들어진 계정을 쓴다
            db.rollback()
            user = db.scalar(sa.select(User).where(User.device_key_hash == key_hash))
            if user is None:
                raise
        db.refresh(user)
        db.commit()
    if user.is_deleted:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="사용할 수 없는 기기 계정입니다.")
    return _issue_token(user)


@router.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 가입된 이메일입니다."
        ) from None
    db.refresh(user)
    db.commit()
    return _issue_token(user)


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(sa.select(User).where(User.email == body.email))
    password_hash = user.password_hash if user is not None and not user.is_deleted else None
    if not verify_password(body.password, password_hash) or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )
    return _issue_token(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    """이 사용자에게 발급된 모든 토큰을 무효화한다 (모든 기기에서 로그아웃)."""
    user.token_version += 1
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=user.id, email=user.email, timezone=user.timezone, created_at=user.created_at
    )
