"""Eat-First 라우트: 오늘 먼저 먹을 것 + 노출 기록."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import User
from app.schemas.eat_first import EatFirstEntry, EatFirstResponse, ReasonResponse
from app.schemas.inventory import InventoryItemResponse
from app.services.eat_first import Algorithm
from app.services.recommendations import create_batch, mark_shown

router = APIRouter(prefix="/eat-first", tags=["eat-first"])


@router.post("", response_model=EatFirstResponse, status_code=status.HTTP_201_CREATED)
def eat_first(
    limit: int = Query(default=3, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EatFirstResponse:
    """상위 N 개를 계산하고 기록한다. 화면에 그린 뒤 /shown 을 호출해야 노출로 집계된다."""
    algorithm = Algorithm(get_settings().eat_first_algorithm)
    batch = create_batch(db, user, algorithm, limit)
    db.commit()
    return EatFirstResponse(
        batch_id=batch.batch_id,
        algorithm_version=batch.algorithm.value,
        local_date=batch.local_date,
        entries=[
            EatFirstEntry(
                recommendation_id=recommendation.id,
                rank=ranked.rank,
                score=ranked.score,
                reasons=[
                    ReasonResponse(code=reason.code, n=reason.n, text=reason.text)
                    for reason in ranked.reasons
                ],
                item=InventoryItemResponse.model_validate(ranked.item),
            )
            for recommendation, ranked in batch.entries
        ],
    )


@router.post("/{batch_id}/shown", status_code=status.HTTP_204_NO_CONTENT)
def shown(
    batch_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    if mark_shown(db, user, batch_id) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="추천을 찾을 수 없습니다.")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
