"""기본 스키마 동작 검증."""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.enums import InventoryStatus, ProductSource
from app.models import InventoryItem, Product, User
from tests.conftest import make_item


def test_create_user(db: Session) -> None:
    user = User()
    db.add(user)
    db.flush()

    assert user.id is not None
    assert user.deleted_at is None


def test_create_inventory_item(db: Session, user: User) -> None:
    item = make_item(db, user, custom_name="두부", expiry_date=date(2026, 8, 20))

    assert item.id is not None
    assert item.custom_name == "두부"
    # status 는 DB server_default 로 ACTIVE 가 들어간다.
    db.refresh(item)
    assert item.status == InventoryStatus.ACTIVE


def test_create_inventory_item_without_product(db: Session, user: User) -> None:
    """사용자 직접 입력 식품은 Product 행 없이 등록 가능해야 한다."""
    item = make_item(db, user, custom_name="직접입력한 반찬")

    assert item.product_id is None
    assert db.scalar(sa.select(sa.func.count()).select_from(Product)) == 0


def test_multiple_inventory_items_share_one_product(db: Session, user: User) -> None:
    """같은 제품을 여러 번 사면 InventoryItem 이 여러 행으로 분리된다."""
    product = Product(canonical_name="서울우유 1L", source=ProductSource.MANUAL)
    db.add(product)
    db.flush()

    first = make_item(db, user, custom_name="우유", product_id=product.id)
    second = make_item(db, user, custom_name="우유", product_id=product.id)

    assert first.id != second.id
    assert first.product_id == second.product_id


def test_same_product_different_expiry_batches(db: Session, user: User) -> None:
    """같은 제품이라도 소비기한이 다른 batch 를 각각 관리할 수 있어야 한다."""
    product = Product(canonical_name="계란 10구")
    db.add(product)
    db.flush()

    make_item(db, user, custom_name="계란", product_id=product.id, expiry_date=date(2026, 8, 20))
    make_item(db, user, custom_name="계란", product_id=product.id, expiry_date=date(2026, 9, 1))

    expiry_dates = db.scalars(
        sa.select(InventoryItem.expiry_date).where(InventoryItem.product_id == product.id)
    ).all()

    assert sorted(d for d in expiry_dates if d is not None) == [
        date(2026, 8, 20),
        date(2026, 9, 1),
    ]
