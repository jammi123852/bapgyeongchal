"""SQLAlchemy Declarative Base 와 공통 Mixin.

시간 처리 원칙 (docs/mvp-v0_1-freeze.md):
- 시각(timestamp) 은 전부 timezone-aware UTC (`timestamptz`).
- 날짜(expiry_date 등) 는 시각이 없는 `DATE`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# alembic autogenerate 와 마이그레이션 안정성을 위해 제약조건 이름 규칙을 고정한다.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def enum_column(enum_cls: type[PyEnum], constraint_name: str) -> sa.Enum:
    """enum 을 VARCHAR + CHECK 제약으로 매핑한다.

    PostgreSQL native ENUM 타입 대신 VARCHAR + CHECK 를 쓰는 이유:
    native ENUM 은 값 추가/삭제 시 ALTER TYPE 이 필요해 마이그레이션과 downgrade 가
    번거롭다. VARCHAR + CHECK 는 DB 레벨 무결성을 그대로 유지하면서
    마이그레이션이 단순하다. (v0.1 규모에서 성능 차이는 무시 가능)
    """
    return sa.Enum(
        enum_cls,
        name=constraint_name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """생성/수정 시각. DB 서버 시계를 사용해 클라이언트 시계 오차를 배제한다."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class SoftDeleteMixin:
    """soft delete.

    물리 삭제를 하지 않는 이유: 실수 삭제 복구가 가능해야 하고,
    삭제된 항목이 통계에서 사라지면 폐기율 지표가 낙관적으로 왜곡된다.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


def not_deleted(model: Any) -> sa.ColumnElement[bool]:
    """soft delete 되지 않은 행만 고르는 조건.

    전역 이벤트 훅으로 자동 필터링하지 않고 명시적 조건을 쓰는 이유:
    자동 필터는 '왜 이 행이 안 나오는지' 추적이 어렵고,
    삭제된 행을 일부러 조회해야 하는 통계 쿼리에서 우회가 필요해진다.
    """
    return model.deleted_at.is_(None)
