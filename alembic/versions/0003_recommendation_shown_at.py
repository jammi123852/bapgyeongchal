"""recommendations.shown_at (Step 7)

추천을 계산한 시각(created_at)과 앱 화면에 실제로 보인 시각(shown_at)을 분리한다.
docs/mvp-v0_1-freeze.md 8-3: 서버가 계산만 하고 안 보였으면 노출이 아니다.

Revision ID: 0003_recommendation_shown_at
Revises: 0002_user_auth
Create Date: 2026-09-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_recommendation_shown_at"
down_revision: Union[str, None] = "0002_user_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recommendations", sa.Column("shown_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("recommendations", "shown_at")
