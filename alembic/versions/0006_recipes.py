"""recipes (임박 재료 요리 추천: 식약처 + 유튜브)

Revision ID: 0006_recipes
Revises: 0005_device_account
Create Date: 2026-09-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0006_recipes"
down_revision: Union[str, None] = "0005_device_account"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recipes",
        sa.Column("id", PGUUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source",
            sa.Enum("FOODSAFETY", "YOUTUBE", name="recipe_source", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("ingredients", JSONB(), nullable=False),
        sa.Column("steps", JSONB(), nullable=True),
        sa.Column("channel_title", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "external_id", name=op.f("uq_recipes_source_external_id")),
    )


def downgrade() -> None:
    op.drop_table("recipes")
