"""Recipe — 임박 재료 요리 추천용 레시피.

ingredients 는 [{"name": 원래 표기, "key": 정규화 키, "pantry": 기본 양념 여부}] (app/services/ingredients.py).
식약처 레시피만 steps(조리 순서)를 저장한다. 유튜브는 영상 링크로 대신한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import RecipeSource
from app.db.base import Base, TimestampMixin, enum_column, uuid_pk


class Recipe(TimestampMixin, Base):
    __tablename__ = "recipes"
    __table_args__ = (sa.UniqueConstraint("source", "external_id", name="uq_recipes_source_external_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    source: Mapped[RecipeSource] = mapped_column(enum_column(RecipeSource, "recipe_source"), nullable=False)
    # FOODSAFETY: RCP_SEQ, YOUTUBE: 영상 ID
    external_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    category: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    ingredients: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    steps: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    channel_title: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # 외부 데이터를 마지막으로 받은 시각 (유튜브 API 정책상 주기적 갱신 필요 여부 판단용)
    fetched_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
