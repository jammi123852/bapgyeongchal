"""InventoryItemEvent 저장 검증.

저장 방식: 변경된 필드만 previous_values / new_values 에 담는다.
(CREATED 만 예외적으로 초기값 전체를 new_values 에 담는다.)
"""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.enums import Actor, InventoryEventType
from app.models import InventoryItemEvent, User
from tests.conftest import make_item


def test_created_event_stores_initial_values(db: Session, user: User) -> None:
    item = make_item(db, user, custom_name="두부", expiry_date=date(2026, 8, 20))

    event = InventoryItemEvent(
        inventory_item_id=item.id,
        user_id=user.id,
        event_type=InventoryEventType.CREATED,
        actor=Actor.USER,
        previous_values=None,
        new_values={"custom_name": "두부", "expiry_date": "2026-08-20"},
    )
    db.add(event)
    db.flush()
    db.refresh(event)

    assert event.previous_values is None
    assert event.new_values["custom_name"] == "두부"


def test_expiry_changed_event_stores_only_changed_field(db: Session, user: User) -> None:
    item = make_item(db, user, expiry_date=date(2026, 8, 20))

    db.add(
        InventoryItemEvent(
            inventory_item_id=item.id,
            user_id=user.id,
            event_type=InventoryEventType.EXPIRY_CHANGED,
            actor=Actor.USER,
            previous_values={"expiry_date": "2026-08-20"},
            new_values={"expiry_date": "2026-08-25"},
        )
    )
    item.expiry_date = date(2026, 8, 25)
    db.flush()

    events = db.scalars(
        sa.select(InventoryItemEvent).where(InventoryItemEvent.inventory_item_id == item.id)
    ).all()

    assert len(events) == 1
    assert set(events[0].new_values.keys()) == {"expiry_date"}
    assert events[0].previous_values["expiry_date"] == "2026-08-20"


def test_event_history_is_ordered(db: Session, user: User) -> None:
    item = make_item(db, user)

    for event_type in (
        InventoryEventType.CREATED,
        InventoryEventType.OPENED_DATE_CHANGED,
        InventoryEventType.STATUS_CHANGED,
    ):
        db.add(
            InventoryItemEvent(
                inventory_item_id=item.id,
                user_id=user.id,
                event_type=event_type,
                actor=Actor.USER,
            )
        )
        db.flush()

    stored = db.scalars(
        sa.select(InventoryItemEvent)
        .where(InventoryItemEvent.inventory_item_id == item.id)
        .order_by(InventoryItemEvent.created_at)
    ).all()

    assert len(stored) == 3
    assert stored[0].event_type == InventoryEventType.CREATED
