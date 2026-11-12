"""remaining_ratio 제약 검증 (0.0 ~ 1.0, null 허용)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User
from tests.conftest import make_item


def test_remaining_ratio_can_be_null(db: Session, user: User) -> None:
    """수량을 모르는 사용자가 많으므로 필수 입력이 아니다."""
    item = make_item(db, user, remaining_ratio=None)
    assert item.remaining_ratio is None


@pytest.mark.parametrize("value", ["0", "0.25", "0.5", "1"])
def test_remaining_ratio_accepts_valid_range(db: Session, user: User, value: str) -> None:
    item = make_item(db, user, remaining_ratio=Decimal(value))
    db.refresh(item)
    assert item.remaining_ratio == Decimal(value)


@pytest.mark.parametrize("value", ["-0.01", "1.01"])
def test_remaining_ratio_rejects_out_of_range(db: Session, user: User, value: str) -> None:
    with pytest.raises(IntegrityError):
        make_item(db, user, remaining_ratio=Decimal(value))
    db.rollback()
