"""User.

Step 3 에서 이메일 + 비밀번호 인증을 붙인다.
- email 은 소문자로 정규화해 저장하고 unique 로 막는다.
- 비밀번호 원문은 저장하지 않고 bcrypt 해시만 저장한다.
- token_version 을 올리면 그 이전에 발급된 토큰이 모두 무효가 된다 (로그아웃).

2026-09-30 로그인 화면 제거: 앱은 기기별 자동 계정을 쓴다 (migration 0005).
- 기기 계정은 email·password_hash 가 없고 device_key_hash(기기 키의 sha256)만 있다.
- 이메일 계정 경로(/auth/signup·login)는 서버에 남아 있지만 앱에서는 쓰지 않는다.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, uuid_pk


class User(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint("email IS NOT NULL OR device_key_hash IS NOT NULL", name="has_identity"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str | None] = mapped_column(sa.Text, nullable=True, unique=True)
    password_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    device_key_hash: Mapped[str | None] = mapped_column(sa.Text, nullable=True, unique=True)
    # 사용자 로컬 날짜 기준 집계용 (docs/mvp-v0_1-freeze.md 7-1 #5)
    timezone: Mapped[str] = mapped_column(
        sa.Text, nullable=False, server_default="Asia/Seoul"
    )
    token_version: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
