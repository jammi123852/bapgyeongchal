"""SoloSafe FastAPI 애플리케이션 (v0.1 Step 1).

이 단계에는 바코드/OCR/레시피/알림/ML/회수/건강 기능이 없다.
백엔드와 DB 연결을 검증하는 최소 구성만 포함한다.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health as health_routes
from app.core.config import get_settings
from app.db.session import SessionLocal, check_database_connection

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """기동 시 DB 연결을 한 번 확인하고 로그로만 남긴다.

    연결 실패로 프로세스를 죽이지는 않는다. DB 가 늦게 뜨는 로컬 환경에서
    앱이 계속 재시작되는 것을 막기 위해서다. 상태는 /health/db 로 확인한다.
    """
    with SessionLocal() as db:
        if check_database_connection(db):
            logger.info("database connection: ok")
        else:
            logger.warning("database connection: failed (see /health/db)")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.include_router(health_routes.router)
    return app


app = create_app()
