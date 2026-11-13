"""재고 API 검증 (Step 4).

완료조건: 필수 입력 최소화, 임박순 목록, 수정 이력, soft delete,
그리고 Step 3 에서 이월된 '다른 사용자 재고 접근 차단'.
"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import InventoryEventType
from app.models import InventoryItem, InventoryItemEvent
from tests.conftest import signup_headers


def create(client: TestClient, headers: dict[str, str], **body: object) -> dict:
    response = client.post("/inventory", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def event_types(db: Session, item_id: str) -> list[InventoryEventType]:
    return list(
        db.scalars(
            sa.select(InventoryItemEvent.event_type)
            .where(InventoryItemEvent.inventory_item_id == item_id)
            .order_by(InventoryItemEvent.created_at, InventoryItemEvent.id)
        )
    )


def test_create_with_only_name_and_expiry(api: TestClient) -> None:
    headers = signup_headers(api)

    item = create(api, headers, custom_name="  두부 ", expiry_date="2026-10-01")

    assert item["custom_name"] == "두부"
    assert item["expiry_date"] == "2026-10-01"
    assert item["status"] == "ACTIVE"
    assert item["remaining_ratio"] == "1.00"


def test_create_with_name_only_is_allowed(api: TestClient) -> None:
    headers = signup_headers(api)

    item = create(api, headers, custom_name="엄마 반찬")

    assert item["expiry_date"] is None


def test_create_rejects_blank_name(api: TestClient) -> None:
    headers = signup_headers(api)

    response = api.post("/inventory", json={"custom_name": "   "}, headers=headers)

    assert response.status_code == 422


def test_create_records_created_event_with_initial_values(api: TestClient, db: Session) -> None:
    headers = signup_headers(api)
    item = create(api, headers, custom_name="우유", expiry_date="2026-10-03")

    event = db.scalar(
        sa.select(InventoryItemEvent).where(InventoryItemEvent.inventory_item_id == item["id"])
    )

    assert event is not None
    assert event.event_type == InventoryEventType.CREATED
    assert event.new_values["expiry_date"] == "2026-10-03"
    assert event.new_values["status"] == "ACTIVE"


def test_list_orders_by_expiry_with_missing_expiry_last(api: TestClient) -> None:
    headers = signup_headers(api)
    create(api, headers, custom_name="기한없음")
    create(api, headers, custom_name="나중", expiry_date="2026-10-10")
    create(api, headers, custom_name="먼저", expiry_date="2026-10-01")

    names = [row["custom_name"] for row in api.get("/inventory", headers=headers).json()]

    assert names == ["먼저", "나중", "기한없음"]


def test_update_records_only_changed_fields(api: TestClient, db: Session) -> None:
    headers = signup_headers(api)
    item = create(api, headers, custom_name="요거트", expiry_date="2026-10-05")

    response = api.patch(
        f"/inventory/{item['id']}",
        json={"expiry_date": "2026-10-07", "opened_date": "2026-09-28", "custom_name": "요거트"},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["expiry_date"] == "2026-10-07"
    # 테스트는 한 트랜잭션 안이라 created_at(now())이 같으므로 순서가 아닌 구성으로 검증한다.
    # custom_name 은 같은 값이라 이벤트가 없어야 한다.
    assert sorted(event_types(db, item["id"])) == sorted(
        [
            InventoryEventType.CREATED,
            InventoryEventType.EXPIRY_CHANGED,
            InventoryEventType.OPENED_DATE_CHANGED,
        ]
    )
    expiry_event = db.scalar(
        sa.select(InventoryItemEvent).where(
            InventoryItemEvent.inventory_item_id == item["id"],
            InventoryItemEvent.event_type == InventoryEventType.EXPIRY_CHANGED,
        )
    )
    assert expiry_event is not None
    assert expiry_event.previous_values == {"expiry_date": "2026-10-05"}
    assert expiry_event.new_values == {"expiry_date": "2026-10-07"}


def test_update_rejects_null_name(api: TestClient) -> None:
    headers = signup_headers(api)
    item = create(api, headers, custom_name="김치")

    response = api.patch(f"/inventory/{item['id']}", json={"custom_name": None}, headers=headers)

    assert response.status_code == 422


def test_soft_delete_hides_item_but_keeps_row(api: TestClient, db: Session) -> None:
    headers = signup_headers(api)
    item = create(api, headers, custom_name="햄")

    assert api.delete(f"/inventory/{item['id']}", headers=headers).status_code == 204
    assert api.get(f"/inventory/{item['id']}", headers=headers).status_code == 404
    assert api.get("/inventory", headers=headers).json() == []

    row = db.get(InventoryItem, item["id"])
    assert row is not None and row.deleted_at is not None
    assert sorted(event_types(db, item["id"])) == sorted(
        [InventoryEventType.CREATED, InventoryEventType.DELETED]
    )


def test_other_users_item_is_invisible_and_untouchable(api: TestClient) -> None:
    owner = signup_headers(api)
    intruder = signup_headers(api)
    item = create(api, owner, custom_name="내 계란", expiry_date="2026-10-02")
    url = f"/inventory/{item['id']}"

    assert api.get("/inventory", headers=intruder).json() == []
    assert api.get(url, headers=intruder).status_code == 404
    assert api.patch(url, json={"custom_name": "뺏음"}, headers=intruder).status_code == 404
    assert api.delete(url, headers=intruder).status_code == 404

    # 주인 쪽 데이터는 그대로다.
    mine = api.get(url, headers=owner).json()
    assert mine["custom_name"] == "내 계란"


def test_inventory_requires_login(api: TestClient) -> None:
    assert api.get("/inventory").status_code == 401
    assert api.post("/inventory", json={"custom_name": "x"}).status_code == 401
