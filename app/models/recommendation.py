"""Recommendation — 특정 시점 ranking 결과 1행.

feature_snapshot 을 저장하는 이유:
InventoryItem 은 UPDATE 로 덮어써지므로 '추천 당시 며칠 남았었는지'를
나중에 소급 재구성하는 것이 원리적으로 불가능하다.
따라서 추천 생성 시점의 feature 를 그대로 보존한다.

recommendation_batch_id 를 두는 이유:
'특정 시각에 냉장고 전체를 ranking 했다'는 사실을 재현하기 위해서다.
같은 실행에서 만들어진 모든 행은 같은 batch id 를 가진다.

주의: 여기에는 인과 해석(예: 추천 때문에 먹었다)을 저장하지 않는다.
사실(무엇을 몇 등으로 추천했는가)만 남긴다.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, uuid_pk


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        sa.CheckConstraint("rank >= 1", name="rank_positive"),
        # 같은 batch 안에서 같은 재고가 두 번 등장할 수 없다.
        sa.UniqueConstraint(
            "recommendation_batch_id", "inventory_item_id", name="uq_batch_item"
        ),
        sa.Index("ix_recommendations_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()

    recommendation_batch_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    score: Mapped[Decimal] = mapped_column(sa.Numeric(12, 6), nullable=False)
    rank: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    # 사용자에게 보여줄 이유 코드 목록. 예: [{"code": "expiry_d1"}]
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    algorithm_version: Mapped[str] = mapped_column(sa.Text, nullable=False)

    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # snapshot 구조가 바뀌어도 과거 데이터를 해석할 수 있어야 한다.
    snapshot_schema_version: Mapped[str] = mapped_column(sa.Text, nullable=False)

    created_at: Mapped[Any] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
