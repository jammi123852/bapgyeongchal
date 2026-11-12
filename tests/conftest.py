"""pytest 공통 fixture.

테스트는 실제 PostgreSQL 을 사용한다. (JSONB, timestamptz, CHECK 제약은
SQLite 로 대체 검증할 수 없다.)

스키마는 alembic migration 으로 만든다. 즉 테스트가 migration 자체를 함께 검증한다.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import create_app_engine
from app.models import InventoryItem, User

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def test_engine() -> Generator[Engine, None, None]:
    """테스트 전용 DB 에 migration 을 적용한 엔진.

    안전장치: TEST_DATABASE_URL 이 없으면 실행하지 않는다.
    (개발 DB 를 실수로 초기화하는 것을 막는다.)
    """
    settings = get_settings()
    url = settings.test_database_url
    if not url:
        pytest.fail("TEST_DATABASE_URL 이 설정되지 않았습니다. .env 를 확인하세요.")
    if url == settings.database_url:
        pytest.fail("TEST_DATABASE_URL 이 DATABASE_URL 과 같습니다. 분리해야 합니다.")

    engine = create_app_engine(url)

    # 매 세션마다 깨끗한 상태에서 migration 을 검증한다.
    with engine.begin() as conn:
        conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(sa.text("CREATE SCHEMA public"))

    alembic_cfg = AlembicConfig(os.path.join(PROJECT_ROOT, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(PROJECT_ROOT, "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = url
    command.upgrade(alembic_cfg, "head")

    yield engine

    engine.dispose()


@pytest.fixture
def db(test_engine: Engine) -> Generator[Session, None, None]:
    """테스트마다 트랜잭션을 열고 끝나면 rollback 한다 (테스트 간 격리)."""
    connection = test_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def user(db: Session) -> User:
    user = User()
    db.add(user)
    db.flush()
    return user


def make_item(db: Session, user: User, **kwargs: object) -> InventoryItem:
    """테스트용 InventoryItem 생성 헬퍼."""
    defaults: dict[str, object] = {"custom_name": f"테스트식품-{uuid.uuid4().hex[:6]}"}
    defaults.update(kwargs)
    item = InventoryItem(user_id=user.id, **defaults)  # type: ignore[arg-type]
    db.add(item)
    db.flush()
    return item
