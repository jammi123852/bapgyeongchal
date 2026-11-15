"""Eat-First 응답과 feature_snapshot 계약 (docs/mvp-v0_1-freeze.md 8-2).

feature_snapshot 은 추천 생성 시점에 한 번 기록하고 수정하지 않는다.
필드를 바꾸면 SNAPSHOT_SCHEMA_VERSION 을 올린다 (과거 데이터 해석 보장).
추천 시스템 자신의 출력(과거 추천·무시 횟수)은 넣지 않는다 (feedback loop 방지).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.inventory import InventoryItemResponse

SNAPSHOT_SCHEMA_VERSION = "1"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SnapshotItem(_Strict):
    inventory_item_id: uuid.UUID
    days_to_expiry: int | None
    has_expiry: bool
    days_since_purchase: int | None
    days_since_open: int | None
    is_opened: bool
    days_to_effective_date: int | None
    remaining_ratio: float | None
    storage_type: str | None
    has_product_link: bool


class SnapshotContext(_Strict):
    inventory_active_count: int
    # 소비기한이 오늘+3일 이내(이미 지난 것 포함)인 활성 재고 수
    inventory_expiring_3d_count: int
    user_days_since_signup: int
    user_action_count_total: int
    weekday: int  # 월=0 ... 일=6 (사용자 로컬)
    hour_local: int


class SnapshotAlgorithm(_Strict):
    version: str
    score: float
    rank: int


class FeatureSnapshotV1(_Strict):
    snapshot_version: Literal["1"]
    captured_at: datetime
    local_date: date
    item: SnapshotItem
    context: SnapshotContext
    algorithm: SnapshotAlgorithm


class ReasonResponse(BaseModel):
    code: str
    n: int | None = None
    text: str


class EatFirstEntry(BaseModel):
    recommendation_id: uuid.UUID
    rank: int
    score: Decimal
    reasons: list[ReasonResponse]
    item: InventoryItemResponse


class EatFirstResponse(BaseModel):
    batch_id: uuid.UUID
    algorithm_version: str
    local_date: date
    entries: list[EatFirstEntry]
