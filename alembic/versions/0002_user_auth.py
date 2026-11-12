"""user auth columns (Step 3)

users 에 email / password_hash / timezone / token_version 을 추가한다.

주의: email, password_hash 는 NOT NULL 이고 기본값이 없다.
기존 users 행이 있으면 upgrade 가 실패한다. v0.1 로컬 개발 DB 는 비어 있다는 전제다.

Revision ID: 0002_user_auth
Revises: 0001_initial_schema
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_user_auth"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.Text(), nullable=False))
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=False))
    op.add_column(
        "users",
        sa.Column("timezone", sa.Text(), server_default="Asia/Seoul", nullable=False),
    )
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "token_version")
    op.drop_column("users", "timezone")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
