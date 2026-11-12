"""soft delete 동작 검증.

구현 방식 결정:
전역 자동 필터(이벤트 훅)를 쓰지 않고, 명시적 조건 함수 not_deleted() 를 사용한다.
자동 필터는 '왜 이 행이 안 나오는지' 추적이 어렵고, 삭제분을 포함해야 하는
통계 쿼리에서 우회가 필요해지기 때문이다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.db.base import not_deleted
from app.models import InventoryItem, User
from tests.conftest import make_item


def test_soft_deleted_item_is_excluded_from_active_query(db: Session, user: User) -> None:
    kept = make_item(db, user, custom_name="남는 것")
    removed = make_item(db, user, custom_name="지운 것")

    removed.deleted_at = datetime.now(timezone.utc)
    db.flush()

    active = db.scalars(
        sa.select(InventoryItem).where(
            InventoryItem.user_id == user.id,
            not_deleted(InventoryItem),
        )
    ).all()

    assert [item.id for item in active] == [kept.id]


def test_soft_deleted_row_still_exists_physically(db: Session, user: User) -> None:
    """물리 삭제가 아니므로 통계/복구를 위해 행은 남아 있어야 한다."""
    item = make_item(db, user)
    item.deleted_at = datetime.now(timezone.utc)
    db.flush()

    total = db.scalar(
        sa.select(sa.func.count())
        .select_from(InventoryItem)
        .where(InventoryItem.user_id == user.id)
    )

    assert total == 1
    assert item.is_deleted is True


def test_restore_clears_deleted_at(db: Session, user: User) -> None:
    item = make_item(db, user)
    item.deleted_at = datetime.now(timezone.utc)
    db.flush()

    item.deleted_at = None
    db.flush()

    assert item.is_deleted is False
