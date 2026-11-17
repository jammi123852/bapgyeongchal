"""inventory_items.expiry_source (OCR 도입)

소비기한이 손입력(MANUAL)인지 OCR 확인값(OCR)인지 구분한다.
기존 행은 모두 손입력이었으므로 MANUAL 로 채워진다.

Revision ID: 0004_expiry_source
Revises: 0003_recommendation_shown_at
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_expiry_source"
down_revision: Union[str, None] = "0003_recommendation_shown_at"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inventory_items",
        sa.Column(
            "expiry_source",
            sa.Enum("MANUAL", "OCR", name="expiry_source", native_enum=False, create_constraint=True),
            server_default="MANUAL",
            nullable=False,
        ),
    )


def downgrade() -> None:
    # 컬럼을 지우면 그 컬럼의 CHECK 제약(ck_inventory_items_expiry_source)도 함께 지워진다.
    op.drop_column("inventory_items", "expiry_source")
