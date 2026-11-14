"""One-tap action 기록.

행동(UserActionType)과 결과 상태(InventoryStatus)를 분리해 둘 다 남긴다.

| 행동                | 결과 상태  | remaining_ratio      |
|---------------------|-----------|----------------------|
| CONSUMED            | CONSUMED  | 0                    |
| PARTIALLY_CONSUMED  | ACTIVE    | 사용자가 고른 값      |
| DISCARDED           | DISCARDED | 그대로 (버린 양 보존) |
| MARKED_EXPIRED      | EXPIRED   | 그대로               |
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.enums import Actor, InventoryStatus, UserActionType
from app.models import InventoryItem, Recommendation, UserAction
from app.services.inventory import apply_changes

RESULT_STATUS: dict[UserActionType, InventoryStatus] = {
    UserActionType.CONSUMED: InventoryStatus.CONSUMED,
    UserActionType.PARTIALLY_CONSUMED: InventoryStatus.ACTIVE,
    UserActionType.DISCARDED: InventoryStatus.DISCARDED,
    UserActionType.MARKED_EXPIRED: InventoryStatus.EXPIRED,
}


class ActionError(Exception):
    """요청이 현재 재고 상태와 맞지 않는다. status_code 는 API 응답 코드."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def record_action(
    db: Session,
    item: InventoryItem,
    action_type: UserActionType,
    remaining_ratio: Decimal | None = None,
    recommendation_id: uuid.UUID | None = None,
) -> UserAction:
    if item.status != InventoryStatus.ACTIVE:
        raise ActionError(409, "이미 처리된 재고입니다.")

    if recommendation_id is not None:
        recommendation = db.get(Recommendation, recommendation_id)
        if (
            recommendation is None
            or recommendation.user_id != item.user_id
            or recommendation.inventory_item_id != item.id
        ):
            raise ActionError(422, "이 재고에 대한 추천이 아닙니다.")

    previous_ratio = item.remaining_ratio
    current = previous_ratio if previous_ratio is not None else Decimal("1")

    if action_type == UserActionType.PARTIALLY_CONSUMED:
        if remaining_ratio is None:
            raise ActionError(422, "남은 양을 선택해 주세요.")
        if not Decimal("0") < remaining_ratio < current:
            raise ActionError(422, "남은 양은 0보다 크고 지금 남은 양보다 작아야 합니다.")
        resulting_ratio = remaining_ratio
    elif remaining_ratio is not None:
        raise ActionError(422, "남은 양은 '일부 먹음'에서만 입력합니다.")
    elif action_type == UserActionType.CONSUMED:
        resulting_ratio = Decimal("0")
    else:
        resulting_ratio = previous_ratio

    action = UserAction(
        user_id=item.user_id,
        inventory_item_id=item.id,
        recommendation_id=recommendation_id,
        action_type=action_type,
        actor=Actor.USER,
        previous_remaining_ratio=previous_ratio,
        resulting_remaining_ratio=resulting_ratio,
    )
    db.add(action)
    apply_changes(
        db,
        item,
        {"status": RESULT_STATUS[action_type], "remaining_ratio": resulting_ratio},
    )
    db.flush()
    return action
