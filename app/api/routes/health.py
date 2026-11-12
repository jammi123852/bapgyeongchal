"""health check 라우트."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import check_database_connection, get_db
from app.schemas.health import DatabaseHealthResponse, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """애플리케이션 자체 생존 확인. DB 를 건드리지 않는다."""
    return HealthResponse(status="ok")


@router.get("/health/db", response_model=DatabaseHealthResponse)
def health_db(response: Response, db: Session = Depends(get_db)) -> DatabaseHealthResponse:
    """DB 연결 확인. 실패 시 503 을 반환한다."""
    if not check_database_connection(db):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return DatabaseHealthResponse(status="error", database="error")
    return DatabaseHealthResponse(status="ok", database="ok")
