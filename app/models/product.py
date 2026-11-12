"""Product — 공식 DB/바코드 제품과 연결 가능한 canonical product.

중요 설계 결정:
사용자가 직접 입력한 모든 식품에 대해 Product 행을 강제로 만들지 않는다.
직접 입력 이름은 InventoryItem.custom_name 에 그대로 저장하며
InventoryItem.product_id 는 nullable 을 유지한다.
(v0.1 은 바코드가 MUST 가 아니므로 products 는 비어 있어도 정상 동작한다.)
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import ProductSource
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, enum_column, uuid_pk


class Product(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        # barcode 는 있을 때만 유일해야 한다 (직접 입력 제품은 barcode 가 없음).
        sa.Index(
            "uq_products_barcode_not_null",
            "barcode",
            unique=True,
            postgresql_where=sa.text("barcode IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()

    canonical_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    barcode: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    source: Mapped[ProductSource | None] = mapped_column(
        enum_column(ProductSource, "product_source"), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
