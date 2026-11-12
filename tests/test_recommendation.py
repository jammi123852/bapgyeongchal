"""Recommendation 저장 검증.

핵심: 추천 생성 당시 상태(feature_snapshot)가 그대로 보존되어야 하고,
같은 ranking 실행이 recommendation_batch_id 로 묶여야 한다.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import Recommendation, User
from tests.conftest import make_item

SNAPSHOT_SCHEMA_VERSION = "1"


def test_feature_snapshot_is_stored_as_json(db: Session, user: User) -> None:
    item = make_item(db, user, expiry_date=date(2026, 8, 20))
    snapshot = {
        "days_to_expiry": 2,
        "days_since_purchase": 4,
        "opened": True,
        "remaining_ratio": 0.5,
    }

    rec = Recommendation(
        recommendation_batch_id=uuid.uuid4(),
        user_id=user.id,
        inventory_item_id=item.id,
        score=Decimal("0.92"),
        rank=1,
        reasons=[{"code": "expiry_d2"}, {"code": "opened_3d"}],
        algorithm_version="baseline1",
        feature_snapshot=snapshot,
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
    )
    db.add(rec)
    db.flush()
    db.refresh(rec)

    assert rec.feature_snapshot == snapshot
    assert rec.feature_snapshot["days_to_expiry"] == 2
    assert rec.reasons[0]["code"] == "expiry_d2"
    assert rec.snapshot_schema_version == SNAPSHOT_SCHEMA_VERSION


def test_batch_groups_multiple_recommendations(db: Session, user: User) -> None:
    """한 번의 ranking 실행에서 나온 후보들이 같은 batch 로 묶인다."""
    batch_id = uuid.uuid4()
    items = [make_item(db, user, custom_name=f"식품{i}") for i in range(3)]

    for rank, item in enumerate(items, start=1):
        db.add(
            Recommendation(
                recommendation_batch_id=batch_id,
                user_id=user.id,
                inventory_item_id=item.id,
                score=Decimal("1") / Decimal(rank),
                rank=rank,
                reasons=[{"code": "expiry_dn"}],
                algorithm_version="baseline1",
                feature_snapshot={"days_to_expiry": rank},
                snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
            )
        )
    db.flush()

    stored = db.scalars(
        sa.select(Recommendation)
        .where(Recommendation.recommendation_batch_id == batch_id)
        .order_by(Recommendation.rank)
    ).all()

    assert len(stored) == 3
    assert [r.rank for r in stored] == [1, 2, 3]
    assert len({r.recommendation_batch_id for r in stored}) == 1


def test_snapshot_survives_inventory_update(db: Session, user: User) -> None:
    """재고가 나중에 바뀌어도 추천 당시 스냅샷은 변하지 않아야 한다.

    이것이 feature_snapshot 을 저장하는 이유다.
    """
    item = make_item(db, user, expiry_date=date(2026, 8, 20), remaining_ratio=Decimal("1"))
    rec = Recommendation(
        recommendation_batch_id=uuid.uuid4(),
        user_id=user.id,
        inventory_item_id=item.id,
        score=Decimal("0.5"),
        rank=1,
        reasons=[],
        algorithm_version="baseline0",
        feature_snapshot={"remaining_ratio": 1.0, "days_to_expiry": 5},
        snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
    )
    db.add(rec)
    db.flush()

    item.remaining_ratio = Decimal("0.25")
    item.expiry_date = date(2026, 9, 30)
    db.flush()
    db.refresh(rec)

    assert rec.feature_snapshot["remaining_ratio"] == 1.0
    assert rec.feature_snapshot["days_to_expiry"] == 5
