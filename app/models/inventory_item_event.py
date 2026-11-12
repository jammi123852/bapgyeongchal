"""InventoryItemEvent — InventoryItem 변경 이력(audit).

저장 방식 결정: **변경된 필드만** previous_values / new_values 에 담는다.

이유:
- 전체 row snapshot 은 같은 값을 반복 저장해 테이블이 빠르게 커지고,
  '무엇이 바뀌었는지'를 읽으려면 매번 diff 를 계산해야 한다.
- 변경 필드만 담으면 이력 조회가 그대로 읽히고,
  특정 필드의 변경 이력(예: expiry_date 수정 횟수)을 바로 집계할 수 있다.
- 예외적으로 CREATED 이벤트는 new_values 에 초기값 전체를 담는다.
  시작점이 있어야 이후 변경을 이어붙여 임의 시점 상태를 복원할 수 있기 때문이다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Actor, InventoryEventType
from app.db.base import Base, enum_column, uuid_pk


class InventoryItemEvent(Base):
    __tablename__ = "inventory_item_events"
    __table_args__ = (
        sa.Index("ix_inventory_item_events_item_created", "inventory_item_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()

    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    event_type: Mapped[InventoryEventType] = mapped_column(
        enum_column(InventoryEventType, "inventory_event_type"), nullable=False
    )
    actor: Mapped[Actor] = mapped_column(
        enum_column(Actor, "actor"), nullable=False, server_default=Actor.USER.value
    )

    previous_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
