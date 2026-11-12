"""DB 엔진 / 세션 관리."""

from __future__ import annotations

from collections.abc import Generator

import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_app_engine(database_url: str, echo: bool = False) -> Engine:
    """엔진 생성.

    세션 타임존을 UTC 로 고정한다. 서버/OS 타임존에 따라 timestamptz 의
    반환 오프셋이 달라지면 테스트와 집계 결과가 환경마다 흔들리기 때문이다.
    """
    return sa.create_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


_settings = get_settings()
engine: Engine = create_app_engine(_settings.database_url, echo=_settings.sql_echo)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 의존성. 요청 단위로 세션을 열고 반드시 닫는다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection(db: Session) -> bool:
    """DB 연결 확인.

    스키마/버전 등 상세 정보를 반환하지 않는다 (외부 노출 최소화).
    """
    try:
        db.execute(sa.text("SELECT 1"))
    except sa.exc.SQLAlchemyError:
        return False
    return True
