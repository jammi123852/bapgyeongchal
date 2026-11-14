"""One-tap action API 검증 (Step 5).

완료조건: 액션 1건이 요청 1번으로 끝나고, user_actions 누락 0건.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import InventoryEventType, UserActionType
from app.models import InventoryItemEvent, UserAction
from tests.conftest import signup_headers


@pytest.fixture
def headers(api: TestClient) -> dict[str, str]:
    return signup_headers(api)


def new_item(api: TestClient, headers: dict[str, str], name: str = "우유") -> str:
    response = api.post(
        "/inventory", json={"custom_name": name, "expiry_date": "2026-10-01"}, headers=headers
    )
    assert response.status_code == 201
    return response.json()["id"]


def act(api: TestClient, headers: dict[str, str], item_id: str, **body: object):
    return api.post(f"/inventory/{item_id}/actions", json=body, headers=headers)


@pytest.mark.parametrize(
    ("action_type", "status", "ratio"),
    [
        ("CONSUMED", "CONSUMED", "0.00"),
        ("DISCARDED", "DISCARDED", "1.00"),
        ("MARKED_EXPIRED", "EXPIRED", "1.00"),
    ],
)
def test_one_tap_sets_status(
    api: TestClient, headers: dict[str, str], db: Session, action_type: str, status: str, ratio: str
) -> None:
    item_id = new_item(api, headers)

    response = act(api, headers, item_id, action_type=action_type)

    assert response.status_code == 201, response.text
    item = response.json()["item"]
    assert item["status"] == status
    assert item["remaining_ratio"] == ratio
    # 처리된 재고는 기본 목록(ACTIVE)에서 빠진다.
    assert api.get("/inventory", headers=headers).json() == []

    action = db.get(UserAction, response.json()["action_id"])
    assert action is not None
    assert action.action_type == UserActionType(action_type)
    assert action.recommendation_id is None


def test_partial_consumption_keeps_item_active(
    api: TestClient, headers: dict[str, str], db: Session
) -> None:
    item_id = new_item(api, headers)

    first = act(api, headers, item_id, action_type="PARTIALLY_CONSUMED", remaining_ratio="0.5")
    second = act(api, headers, item_id, action_type="PARTIALLY_CONSUMED", remaining_ratio="0.25")

    assert first.status_code == second.status_code == 201
    assert second.json()["item"]["status"] == "ACTIVE"
    assert second.json()["item"]["remaining_ratio"] == "0.25"

    actions = db.scalars(
        sa.select(UserAction).where(UserAction.inventory_item_id == item_id)
    ).all()
    history = sorted(
        (str(a.previous_remaining_ratio), str(a.resulting_remaining_ratio)) for a in actions
    )
    assert history == [("0.50", "0.25"), ("1.00", "0.50")]


@pytest.mark.parametrize(
    "body",
    [
        {"action_type": "PARTIALLY_CONSUMED"},  # 남은 양 없음
        {"action_type": "PARTIALLY_CONSUMED", "remaining_ratio": "0"},  # 0 은 CONSUMED 로
        {"action_type": "PARTIALLY_CONSUMED", "remaining_ratio": "1"},  # 줄지 않음
        {"action_type": "CONSUMED", "remaining_ratio": "0.5"},  # 다른 행동에 남은 양
    ],
)
def test_invalid_ratio_requests_are_rejected(
    api: TestClient, headers: dict[str, str], db: Session, body: dict
) -> None:
    item_id = new_item(api, headers)

    response = act(api, headers, item_id, **body)

    assert response.status_code == 422
    count = db.scalar(
        sa.select(sa.func.count()).select_from(UserAction).where(UserAction.inventory_item_id == item_id)
    )
    assert count == 0


def test_cannot_act_twice_on_finished_item(api: TestClient, headers: dict[str, str]) -> None:
    item_id = new_item(api, headers)
    act(api, headers, item_id, action_type="CONSUMED")

    response = act(api, headers, item_id, action_type="DISCARDED")

    assert response.status_code == 409


def test_action_records_status_change_event(
    api: TestClient, headers: dict[str, str], db: Session
) -> None:
    item_id = new_item(api, headers)
    act(api, headers, item_id, action_type="DISCARDED")

    event = db.scalar(
        sa.select(InventoryItemEvent).where(
            InventoryItemEvent.inventory_item_id == item_id,
            InventoryItemEvent.event_type == InventoryEventType.STATUS_CHANGED,
        )
    )

    assert event is not None
    assert event.previous_values == {"status": "ACTIVE"}
    assert event.new_values == {"status": "DISCARDED"}


def test_other_user_cannot_act(api: TestClient, headers: dict[str, str]) -> None:
    item_id = new_item(api, headers)
    intruder = signup_headers(api)

    assert act(api, intruder, item_id, action_type="CONSUMED").status_code == 404
    assert api.get(f"/inventory/{item_id}", headers=headers).json()["status"] == "ACTIVE"


def test_unknown_recommendation_is_rejected(api: TestClient, headers: dict[str, str]) -> None:
    item_id = new_item(api, headers)

    response = act(
        api,
        headers,
        item_id,
        action_type="CONSUMED",
        recommendation_id="00000000-0000-0000-0000-000000000000",
    )

    assert response.status_code == 422
