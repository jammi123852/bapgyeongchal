"""추천 생성 + 기록 (Step 7). 원칙: 로깅 없는 추천은 내보내지 않는다.

흐름:
1. POST /eat-first  → 순위 계산, 상위 N 개를 recommendations 에 batch 로 저장 (shown_at = null)
2. 앱이 화면에 실제로 그린 뒤 POST /eat-first/{batch_id}/shown → shown_at 기록
   서버가 계산만 하고 화면에 안 보였으면 노출이 아니다 (8-3).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.enums import InventoryStatus
from app.db.base import not_deleted
from app.models import InventoryItem, Recommendation, User, UserAction
from app.schemas.eat_first import (
    SNAPSHOT_SCHEMA_VERSION,
    FeatureSnapshotV1,
    SnapshotAlgorithm,
    SnapshotContext,
    SnapshotItem,
)
from app.services.eat_first import Algorithm, Ranked, rank_items

EXPIRING_WINDOW_DAYS = 3


@dataclass
class Batch:
    batch_id: uuid.UUID
    algorithm: Algorithm
    local_date: date
    entries: list[tuple[Recommendation, Ranked]]


def _days(later: date, earlier: date | None) -> int | None:
    return None if earlier is None else (later - earlier).days


def build_snapshot(
    entry: Ranked,
    algorithm: Algorithm,
    captured_at: datetime,
    local_now: datetime,
    context: SnapshotContext,
) -> FeatureSnapshotV1:
    item = entry.item
    today = local_now.date()
    return FeatureSnapshotV1(
        snapshot_version=SNAPSHOT_SCHEMA_VERSION,
        captured_at=captured_at,
        local_date=today,
        item=SnapshotItem(
            inventory_item_id=item.id,
            days_to_expiry=None if item.expiry_date is None else (item.expiry_date - today).days,
            has_expiry=item.expiry_date is not None,
            days_since_purchase=_days(today, item.purchase_date),
            days_since_open=_days(today, item.opened_date),
            is_opened=item.opened_date is not None,
            days_to_effective_date=(
                None if entry.effective_date is None else (entry.effective_date - today).days
            ),
            remaining_ratio=None if item.remaining_ratio is None else float(item.remaining_ratio),
            storage_type=None if item.storage_type is None else item.storage_type.value,
            has_product_link=item.product_id is not None,
        ),
        context=context,
        algorithm=SnapshotAlgorithm(
            version=algorithm.value, score=float(entry.score), rank=entry.rank
        ),
    )


def create_batch(
    db: Session,
    user: User,
    algorithm: Algorithm,
    limit: int,
    now: datetime | None = None,
) -> Batch:
    captured_at = now or datetime.now(UTC)
    local_now = captured_at.astimezone(ZoneInfo(user.timezone))
    today = local_now.date()

    items = list(
        db.scalars(
            sa.select(InventoryItem).where(
                InventoryItem.user_id == user.id,
                InventoryItem.status == InventoryStatus.ACTIVE,
                not_deleted(InventoryItem),
            )
        )
    )
    ranked = rank_items(items, today, algorithm)

    expiring_limit = today + timedelta(days=EXPIRING_WINDOW_DAYS)
    context = SnapshotContext(
        inventory_active_count=len(items),
        inventory_expiring_3d_count=sum(
            1 for i in items if i.expiry_date is not None and i.expiry_date <= expiring_limit
        ),
        user_days_since_signup=(captured_at - user.created_at).days,
        user_action_count_total=db.scalar(
            sa.select(sa.func.count()).select_from(UserAction).where(UserAction.user_id == user.id)
        )
        or 0,
        weekday=local_now.weekday(),
        hour_local=local_now.hour,
    )

    batch_id = uuid.uuid4()
    entries: list[tuple[Recommendation, Ranked]] = []
    for entry in ranked[:limit]:
        snapshot = build_snapshot(entry, algorithm, captured_at, local_now, context)
        recommendation = Recommendation(
            recommendation_batch_id=batch_id,
            user_id=user.id,
            inventory_item_id=entry.item.id,
            score=Decimal(entry.score),
            rank=entry.rank,
            reasons=[reason.as_json() for reason in entry.reasons],
            algorithm_version=algorithm.value,
            feature_snapshot=snapshot.model_dump(mode="json"),
            snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
        )
        db.add(recommendation)
        entries.append((recommendation, entry))
    db.flush()
    return Batch(batch_id, algorithm, today, entries)


def mark_shown(db: Session, user: User, batch_id: uuid.UUID) -> int:
    """batch 의 노출 시각을 기록한다. 처음 한 번만 기록한다. 반환: 해당 batch 행 수."""
    rows = list(
        db.scalars(
            sa.select(Recommendation).where(
                Recommendation.recommendation_batch_id == batch_id,
                Recommendation.user_id == user.id,
            )
        )
    )
    shown_at = datetime.now(UTC)
    for row in rows:
        if row.shown_at is None:
            row.shown_at = shown_at
    db.flush()
    return len(rows)
