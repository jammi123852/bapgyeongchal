"""UserAction — one-tap action 기록.

InventoryStatus(상태) 와 UserActionType(행동) 은 분리되어 있다.
예: MARKED_EXPIRED(행동) → InventoryStatus.EXPIRED(상태)

actor 를 분리한 이유:
사용자가 직접 누른 기록과, 나중에 시스템이 자동 판정할 기록이 섞이면
미래 학습 라벨이 오염된다. SYSTEM action 이 아직 없어도 컬럼은 지금 만든다.

부분 소비 기록:
previous_remaining_ratio / resulting_remaining_ratio 를 함께 남겨
'얼마에서 얼마로 줄었는지'를 사후 재구성할 수 있게 한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Actor, UserActionType
from app.db.base import Base, enum_column, uuid_pk


class UserAction(Base):
    __tablename__ = "user_actions"
    __table_args__ = (
        sa.CheckConstraint(
            "previous_remaining_ratio IS NULL OR "
            "(previous_remaining_ratio >= 0 AND previous_remaining_ratio <= 1)",
            name="previous_remaining_ratio_range",
        ),
        sa.CheckConstraint(
            "resulting_remaining_ratio IS NULL OR "
            "(resulting_remaining_ratio >= 0 AND resulting_remaining_ratio <= 1)",
            name="resulting_remaining_ratio_range",
        ),
        sa.Index("ix_user_actions_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # 목록에서 직접 처리한 경우(추천 경유가 아닌 경우) null 이다.
    recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("recommendations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    action_type: Mapped[UserActionType] = mapped_column(
        enum_column(UserActionType, "user_action_type"), nullable=False
    )
    actor: Mapped[Actor] = mapped_column(
        enum_column(Actor, "actor"), nullable=False, server_default=Actor.USER.value
    )

    previous_remaining_ratio: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(3, 2), nullable=True
    )
    resulting_remaining_ratio: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(3, 2), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
