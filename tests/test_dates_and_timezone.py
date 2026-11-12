"""날짜/시각 타입 검증.

- expiry_date 등 '날짜' 는 시각 없는 DATE
- created_at 등 '시각' 은 timezone-aware UTC
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import User
from tests.conftest import make_item


def test_expiry_date_is_plain_date(db: Session, user: User) -> None:
    item = make_item(db, user, expiry_date=date(2026, 8, 20))
    db.expire_all()
    db.refresh(item)

    assert isinstance(item.expiry_date, date)
    # datetime 은 date 의 subclass 이므로 명시적으로 배제한다.
    assert not isinstance(item.expiry_date, datetime)


def test_date_columns_are_date_type_in_db(db: Session) -> None:
    rows = db.execute(
        sa.text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'inventory_items'
              AND column_name IN ('expiry_date', 'purchase_date', 'opened_date')
            """
        )
    ).all()

    assert {name: dtype for name, dtype in rows} == {
        "expiry_date": "date",
        "purchase_date": "date",
        "opened_date": "date",
    }


def test_timestamps_are_timezone_aware_utc(db: Session, user: User) -> None:
    item = make_item(db, user)
    db.refresh(item)

    assert item.created_at.tzinfo is not None
    assert item.created_at.utcoffset() == timedelta(0)
    assert item.updated_at.utcoffset() == timedelta(0)


def test_timestamp_columns_are_timestamptz_in_db(db: Session) -> None:
    rows = db.execute(
        sa.text(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE column_name IN ('created_at', 'updated_at', 'deleted_at')
              AND table_schema = 'public'
            """
        )
    ).all()

    assert rows, "timestamp 컬럼을 찾지 못했습니다"
    for table_name, column_name, data_type in rows:
        assert data_type == "timestamp with time zone", (
            f"{table_name}.{column_name} 이 timestamptz 가 아닙니다: {data_type}"
        )
