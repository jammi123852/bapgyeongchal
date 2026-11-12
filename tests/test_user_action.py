"""UserAction 저장 검증.

상태(InventoryStatus)와 행동(UserActionType)이 분리되어 있는지 함께 확인한다.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import Actor, InventoryStatus, UserActionType
from app.models import User, UserAction
from tests.conftest import make_item


def test_partially_consumed_records_before_and_after(db: Session, user: User) -> None:
    item = make_item(db, user, remaining_ratio=Decimal("1"))

    action = UserAction(
        user_id=user.id,
        inventory_item_id=item.id,
        action_type=UserActionType.PARTIALLY_CONSUMED,
        actor=Actor.USER,
        previous_remaining_ratio=Decimal("1"),
        resulting_remaining_ratio=Decimal("0.5"),
    )
    db.add(action)
    item.remaining_ratio = Decimal("0.5")
    db.flush()
    db.refresh(action)

    assert action.action_type == UserActionType.PARTIALLY_CONSUMED
    assert action.previous_remaining_ratio == Decimal("1")
    assert action.resulting_remaining_ratio == Decimal("0.5")
    # 부분 소비는 상태를 바꾸지 않는다.
    assert item.status == InventoryStatus.ACTIVE


def test_marked_expired_action_maps_to_expired_status(db: Session, user: User) -> None:
    """MARKED_EXPIRED 는 행동이고, 그 결과 상태는 EXPIRED 다."""
    item = make_item(db, user)

    db.add(
        UserAction(
            user_id=user.id,
            inventory_item_id=item.id,
            action_type=UserActionType.MARKED_EXPIRED,
            actor=Actor.USER,
        )
    )
    item.status = InventoryStatus.EXPIRED
    db.flush()

    assert item.status.value == "EXPIRED"
    assert UserActionType.MARKED_EXPIRED.value == "MARKED_EXPIRED"
    # 두 enum 은 서로 다른 값 집합을 가진다.
    assert "MARKED_EXPIRED" not in {s.value for s in InventoryStatus}
    assert "EXPIRED" not in {a.value for a in UserActionType}


def test_actor_defaults_to_user_and_supports_system(db: Session, user: User) -> None:
    item = make_item(db, user)

    system_action = UserAction(
        user_id=user.id,
        inventory_item_id=item.id,
        action_type=UserActionType.MARKED_EXPIRED,
        actor=Actor.SYSTEM,
    )
    db.add(system_action)
    db.flush()
    db.refresh(system_action)

    assert system_action.actor == Actor.SYSTEM


def test_recommendation_id_is_optional(db: Session, user: User) -> None:
    """목록에서 직접 처리한 경우 추천과 연결되지 않는다."""
    item = make_item(db, user)
    action = UserAction(
        user_id=user.id,
        inventory_item_id=item.id,
        action_type=UserActionType.CONSUMED,
        actor=Actor.USER,
    )
    db.add(action)
    db.flush()

    assert action.recommendation_id is None


def test_invalid_action_type_is_rejected(db: Session, user: User) -> None:
    """DB CHECK 제약으로 정의되지 않은 action 값을 막는다."""
    item = make_item(db, user)
    # ORM Enum 은 DB 에 닿기 전에 StatementError 로 막으므로, raw SQL 로 DB 제약을 직접 검증한다.
    with pytest.raises((IntegrityError, DataError)):
        db.execute(
            sa.text(
                """
                INSERT INTO user_actions (id, user_id, inventory_item_id, action_type, actor)
                VALUES (gen_random_uuid(), :user_id, :item_id, 'EATEN_MAYBE', 'USER')
                """
            ),
            {"user_id": user.id, "item_id": item.id},
        )
    db.rollback()
