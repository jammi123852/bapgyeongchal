"""재고 등록/조회/수정/삭제와 변경 이력 기록.

모든 조회는 user_id 로 제한한다. 다른 사용자의 재고는 '없는 것'과 같게 취급한다(404).
존재 여부 자체를 노출하지 않기 위해 403 을 쓰지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.enums import Actor, InventoryEventType, InventoryStatus
from app.db.base import not_deleted
from app.models import InventoryItem, InventoryItemEvent, User

# 필드 → 이력 유형. 여기에 없는 필드(custom_name, purchase_date)는 이력 유형이 정의돼
# 있지 않아 이벤트를 남기지 않는다 (추천·학습 feature 에 쓰이지 않는 필드).
FIELD_EVENT_TYPES: dict[str, InventoryEventType] = {
    "expiry_date": InventoryEventType.EXPIRY_CHANGED,
    "opened_date": InventoryEventType.OPENED_DATE_CHANGED,
    "storage_type": InventoryEventType.STORAGE_CHANGED,
    "quantity": InventoryEventType.QUANTITY_CHANGED,
    "quantity_unit": InventoryEventType.QUANTITY_CHANGED,
    "remaining_ratio": InventoryEventType.QUANTITY_CHANGED,
    "status": InventoryEventType.STATUS_CHANGED,
}

SNAPSHOT_FIELDS = (
    "custom_name",
    "expiry_date",
    "purchase_date",
    "opened_date",
    "storage_type",
    "quantity",
    "quantity_unit",
    "remaining_ratio",
    "status",
)


def to_json_value(value: Any) -> Any:
    """JSONB 에 넣을 수 있는 값으로 변환한다."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def record_event(
    db: Session,
    item: InventoryItem,
    event_type: InventoryEventType,
    previous_values: dict[str, Any] | None,
    new_values: dict[str, Any] | None,
    actor: Actor = Actor.USER,
) -> None:
    db.add(
        InventoryItemEvent(
            inventory_item_id=item.id,
            user_id=item.user_id,
            event_type=event_type,
            actor=actor,
            previous_values=previous_values,
            new_values=new_values,
        )
    )


def create_item(db: Session, user: User, values: dict[str, Any]) -> InventoryItem:
    item = InventoryItem(user_id=user.id, remaining_ratio=Decimal("1"), **values)
    db.add(item)
    db.flush()
    db.refresh(item)
    # CREATED 는 초기값 전체를 담는다 (이후 변경을 이어붙일 시작점).
    record_event(
        db,
        item,
        InventoryEventType.CREATED,
        None,
        {field: to_json_value(getattr(item, field)) for field in SNAPSHOT_FIELDS},
    )
    db.flush()
    return item


def list_items(
    db: Session, user: User, status: InventoryStatus | None = InventoryStatus.ACTIVE
) -> list[InventoryItem]:
    """기본: 활성 재고를 소비기한 임박순. 기한 없는 항목은 맨 뒤(등록 순)."""
    query = sa.select(InventoryItem).where(
        InventoryItem.user_id == user.id, not_deleted(InventoryItem)
    )
    if status is not None:
        query = query.where(InventoryItem.status == status)
    query = query.order_by(
        InventoryItem.expiry_date.asc().nulls_last(),
        InventoryItem.created_at.asc(),
        InventoryItem.id.asc(),
    )
    return list(db.scalars(query))


def get_item(db: Session, user: User, item_id: uuid.UUID) -> InventoryItem | None:
    return db.scalar(
        sa.select(InventoryItem).where(
            InventoryItem.id == item_id,
            InventoryItem.user_id == user.id,
            not_deleted(InventoryItem),
        )
    )


def apply_changes(
    db: Session,
    item: InventoryItem,
    changes: dict[str, Any],
    actor: Actor = Actor.USER,
) -> None:
    """필드를 바꾸고, 실제로 바뀐 필드만 이력 유형별로 묶어 기록한다."""
    grouped: dict[InventoryEventType, tuple[dict[str, Any], dict[str, Any]]] = {}
    for field, new_value in changes.items():
        old_value = getattr(item, field)
        if old_value == new_value:
            continue
        setattr(item, field, new_value)
        event_type = FIELD_EVENT_TYPES.get(field)
        if event_type is None:
            continue
        previous, new = grouped.setdefault(event_type, ({}, {}))
        previous[field] = to_json_value(old_value)
        new[field] = to_json_value(new_value)

    for event_type, (previous, new) in grouped.items():
        record_event(db, item, event_type, previous, new, actor=actor)
    db.flush()


def soft_delete_item(db: Session, item: InventoryItem) -> None:
    item.deleted_at = datetime.now(UTC)
    record_event(db, item, InventoryEventType.DELETED, None, None)
    db.flush()
