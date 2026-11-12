"""InventoryItem — 사용자의 냉장고 재고 1건."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import InventoryStatus, StorageType
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, enum_column, uuid_pk


class InventoryItem(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "inventory_items"
    __table_args__ = (
        # 수량을 모르는 사용자가 많으므로 nullable 이지만, 값이 있으면 0~1 범위여야 한다.
        sa.CheckConstraint(
            "remaining_ratio IS NULL OR (remaining_ratio >= 0 AND remaining_ratio <= 1)",
            name="remaining_ratio_range",
        ),
        sa.Index("ix_inventory_items_user_status_expiry", "user_id", "status", "expiry_date"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )

    # 사용자가 입력한 이름. product 연결 여부와 무관하게 항상 채운다.
    custom_name: Mapped[str] = mapped_column(sa.Text, nullable=False)

    # 시각이 아니라 '날짜'다. timestamptz 로 두면 23:59 경계에서 하루가 밀린다.
    # 바코드 조회 결과를 이 컬럼에 직접 대입하지 않는다 (개별 포장의 실제 인쇄일만 저장).
    expiry_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    opened_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)

    storage_type: Mapped[StorageType | None] = mapped_column(
        enum_column(StorageType, "storage_type"), nullable=True
    )

    quantity: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 3), nullable=True)
    quantity_unit: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    remaining_ratio: Mapped[Decimal | None] = mapped_column(sa.Numeric(3, 2), nullable=True)

    status: Mapped[InventoryStatus] = mapped_column(
        enum_column(InventoryStatus, "inventory_status"),
        nullable=False,
        server_default=InventoryStatus.ACTIVE.value,
    )
