"""재고 라우트: 등록 / 목록 / 상세 / 수정 / 삭제(soft)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.enums import InventoryStatus
from app.db.session import get_db
from app.models import InventoryItem, User
from app.schemas.inventory import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryItemUpdate,
)
from app.services import inventory as inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])


def get_owned_item(
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InventoryItem:
    """내 재고만 찾는다. 다른 사용자의 재고와 삭제된 재고는 404."""
    item = inventory_service.get_item(db, user, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="재고를 찾을 수 없습니다.")
    return item


@router.post("", response_model=InventoryItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    body: InventoryItemCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InventoryItem:
    item = inventory_service.create_item(db, user, body.model_dump())
    db.commit()
    return item


@router.get("", response_model=list[InventoryItemResponse])
def list_items(
    status_filter: InventoryStatus | None = Query(default=InventoryStatus.ACTIVE, alias="status"),
    include_all: bool = Query(default=False, description="true 면 상태와 무관하게 전부"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[InventoryItem]:
    return inventory_service.list_items(db, user, None if include_all else status_filter)


@router.get("/{item_id}", response_model=InventoryItemResponse)
def get_item(item: InventoryItem = Depends(get_owned_item)) -> InventoryItem:
    return item


@router.patch("/{item_id}", response_model=InventoryItemResponse)
def update_item(
    body: InventoryItemUpdate,
    item: InventoryItem = Depends(get_owned_item),
    db: Session = Depends(get_db),
) -> InventoryItem:
    changes = body.model_dump(exclude_unset=True)
    if "custom_name" in changes and changes["custom_name"] is None:
        raise HTTPException(status_code=422, detail="이름은 비울 수 없습니다.")
    inventory_service.apply_changes(db, item, changes)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item: InventoryItem = Depends(get_owned_item),
    db: Session = Depends(get_db),
) -> Response:
    inventory_service.soft_delete_item(db, item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
