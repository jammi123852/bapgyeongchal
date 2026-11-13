"""재고(InventoryItem) 요청/응답 스키마.

등록 마찰을 줄이기 위해 필수 입력은 이름 하나다. 소비기한은 입력을 권장하지만
모르는 식품(반찬 등)도 저장할 수 있게 비워둘 수 있다. 이 경우 Eat-First 에서
'소비기한이 등록되지 않았어요' 이유와 함께 맨 뒤로 간다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import InventoryStatus, StorageType

NAME_MAX_LENGTH = 100


class InventoryItemCreate(BaseModel):
    custom_name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    expiry_date: date | None = None
    # 아래는 접힌 영역의 선택 입력
    purchase_date: date | None = None
    opened_date: date | None = None
    storage_type: StorageType | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    quantity_unit: str | None = Field(default=None, max_length=20)

    @field_validator("custom_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("이름을 입력해 주세요.")
        return value


class InventoryItemUpdate(BaseModel):
    """부분 수정. 보낸 필드만 바꾼다 (null 을 보내면 값을 지운다)."""

    custom_name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX_LENGTH)
    expiry_date: date | None = None
    purchase_date: date | None = None
    opened_date: date | None = None
    storage_type: StorageType | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    quantity_unit: str | None = Field(default=None, max_length=20)

    @field_validator("custom_name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("이름을 입력해 주세요.")
        return value


class InventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    custom_name: str
    expiry_date: date | None
    purchase_date: date | None
    opened_date: date | None
    storage_type: StorageType | None
    quantity: Decimal | None
    quantity_unit: str | None
    remaining_ratio: Decimal | None
    status: InventoryStatus
    created_at: datetime
    updated_at: datetime
