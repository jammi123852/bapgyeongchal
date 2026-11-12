"""initial schema for SoloSafe v0.1 (Step 1)

users / products / inventory_items / inventory_item_events /
recommendations / user_actions 를 생성한다.

주의: enum 값은 app.core.enums 를 import 하지 않고 문자열로 고정한다.
마이그레이션은 '그 시점의 스키마'를 기록하는 파일이므로,
나중에 애플리케이션 enum 이 바뀌어도 이 파일의 결과가 달라지면 안 된다.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-08-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _enum(*values: str, name: str) -> sa.Enum:
    """VARCHAR + CHECK 방식 enum (native PG ENUM 미사용)."""
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("barcode", sa.Text(), nullable=True),
        sa.Column(
            "source",
            _enum("MANUAL", "C005", "I2570", "HACCP", "OFF", name="product_source"),
            nullable=True,
        ),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    # barcode 는 값이 있을 때만 유일하다 (직접 입력 제품은 barcode 가 없음).
    op.create_index(
        "uq_products_barcode_not_null",
        "products",
        ["barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )

    op.create_table(
        "inventory_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("custom_name", sa.Text(), nullable=False),
        # 날짜는 시각 없는 DATE (23:59 경계 문제 방지)
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("opened_date", sa.Date(), nullable=True),
        sa.Column(
            "storage_type",
            _enum("FRIDGE", "FREEZER", "PANTRY", name="storage_type"),
            nullable=True,
        ),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=True),
        sa.Column("quantity_unit", sa.Text(), nullable=True),
        sa.Column("remaining_ratio", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "status",
            _enum("ACTIVE", "CONSUMED", "DISCARDED", "EXPIRED", name="inventory_status"),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "remaining_ratio IS NULL OR (remaining_ratio >= 0 AND remaining_ratio <= 1)",
            name="remaining_ratio_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_items_user_id", "inventory_items", ["user_id"])
    op.create_index(
        "ix_inventory_items_user_status_expiry",
        "inventory_items",
        ["user_id", "status", "expiry_date"],
    )

    op.create_table(
        "inventory_item_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_type",
            _enum(
                "CREATED",
                "EXPIRY_CHANGED",
                "OPENED_DATE_CHANGED",
                "STORAGE_CHANGED",
                "QUANTITY_CHANGED",
                "STATUS_CHANGED",
                "DELETED",
                "RESTORED",
                name="inventory_event_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "actor",
            _enum("USER", "SYSTEM", name="actor"),
            server_default="USER",
            nullable=False,
        ),
        # 변경된 필드만 담는다 (CREATED 만 예외적으로 초기값 전체).
        sa.Column("previous_values", postgresql.JSONB(), nullable=True),
        sa.Column("new_values", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"], ["inventory_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_inventory_item_events_item_created",
        "inventory_item_events",
        ["inventory_item_id", "created_at"],
    )

    op.create_table(
        "recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        # 같은 ranking 실행에서 생성된 행들을 묶는 키
        sa.Column("recommendation_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.Numeric(12, 6), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        # 추천 당시 상태. 소급 재구성이 불가능하므로 생성 시점에 보존한다.
        sa.Column("feature_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot_schema_version", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("rank >= 1", name="rank_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"], ["inventory_items.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recommendation_batch_id", "inventory_item_id", name="uq_batch_item"
        ),
    )
    op.create_index(
        "ix_recommendations_recommendation_batch_id",
        "recommendations",
        ["recommendation_batch_id"],
    )
    op.create_index(
        "ix_recommendations_inventory_item_id", "recommendations", ["inventory_item_id"]
    )
    op.create_index(
        "ix_recommendations_user_created", "recommendations", ["user_id", "created_at"]
    )

    op.create_table(
        "user_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inventory_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "action_type",
            _enum(
                "CONSUMED",
                "PARTIALLY_CONSUMED",
                "DISCARDED",
                "MARKED_EXPIRED",
                name="user_action_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "actor",
            _enum("USER", "SYSTEM", name="actor"),
            server_default="USER",
            nullable=False,
        ),
        sa.Column("previous_remaining_ratio", sa.Numeric(3, 2), nullable=True),
        sa.Column("resulting_remaining_ratio", sa.Numeric(3, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "previous_remaining_ratio IS NULL OR "
            "(previous_remaining_ratio >= 0 AND previous_remaining_ratio <= 1)",
            name="previous_remaining_ratio_range",
        ),
        sa.CheckConstraint(
            "resulting_remaining_ratio IS NULL OR "
            "(resulting_remaining_ratio >= 0 AND resulting_remaining_ratio <= 1)",
            name="resulting_remaining_ratio_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["inventory_item_id"], ["inventory_items.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"], ["recommendations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_actions_inventory_item_id", "user_actions", ["inventory_item_id"])
    op.create_index("ix_user_actions_recommendation_id", "user_actions", ["recommendation_id"])
    op.create_index("ix_user_actions_user_created", "user_actions", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_table("user_actions")
    op.drop_table("recommendations")
    op.drop_table("inventory_item_events")
    op.drop_table("inventory_items")
    op.drop_index("uq_products_barcode_not_null", table_name="products")
    op.drop_table("products")
    op.drop_table("users")
