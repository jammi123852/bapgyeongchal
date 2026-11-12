"""User.

Step 1 에서는 인증 시스템을 구현하지 않는다.
외부 auth provider 와 연결될 내부 user entity 만 정의한다.
(provider / subject 매핑 컬럼은 인증을 붙이는 Step 3 에서 추가한다.)
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Mapped

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, uuid_pk


class User(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
