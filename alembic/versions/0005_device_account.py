"""기기별 자동 계정 (로그인 화면 제거)

앱이 처음 켜질 때 기기에서 무작위 키를 만들고, 서버는 그 키의 sha256 만 저장한다.
이메일·비밀번호 없이 계정이 생기므로 두 컬럼을 nullable 로 바꾸고,
둘 중 하나(이메일 또는 기기 키)는 반드시 있도록 CHECK 를 건다.

Revision ID: 0005_device_account
Revises: 0004_expiry_source
Create Date: 2026-09-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_device_account"
down_revision: Union[str, None] = "0004_expiry_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("device_key_hash", sa.Text(), nullable=True))
    op.create_unique_constraint(op.f("uq_users_device_key_hash"), "users", ["device_key_hash"])
    op.alter_column("users", "email", existing_type=sa.Text(), nullable=True)
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=True)
    op.create_check_constraint(
        op.f("ck_users_has_identity"), "users", "email IS NOT NULL OR device_key_hash IS NOT NULL"
    )


def downgrade() -> None:
    # 기기 계정 행이 있으면 email NOT NULL 로 되돌릴 수 없다. 기기 계정을 먼저 정리해야 한다.
    op.drop_constraint(op.f("ck_users_has_identity"), "users", type_="check")
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=False)
    op.alter_column("users", "email", existing_type=sa.Text(), nullable=False)
    op.drop_constraint(op.f("uq_users_device_key_hash"), "users", type_="unique")
    op.drop_column("users", "device_key_hash")
