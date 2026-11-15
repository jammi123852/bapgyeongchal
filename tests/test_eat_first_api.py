"""Eat-First API + 추천 기록 검증 (Step 7).

완료조건: 노출 100% 가 로그에 남고, feature_snapshot 이 스키마 검증을 통과한다.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Recommendation
from app.schemas.eat_first import FeatureSnapshotV1
from tests.conftest import signup_headers


def seoul_today() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


@pytest.fixture
def headers(api: TestClient) -> dict[str, str]:
    return signup_headers(api)


def add(api: TestClient, headers: dict[str, str], name: str, days: int | None, **extra: object) -> str:
    body: dict[str, object] = {"custom_name": name, **extra}
    if days is not None:
        body["expiry_date"] = (seoul_today() + timedelta(days=days)).isoformat()
    response = api.post("/inventory", json=body, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def test_returns_top_n_with_reasons_and_logs_them(
    api: TestClient, headers: dict[str, str], db: Session
) -> None:
    add(api, headers, "D-5", 5)
    add(api, headers, "D-1", 1)
    add(api, headers, "기한없음", None)
    add(api, headers, "D-3", 3)

    response = api.post("/eat-first?limit=3", headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["algorithm_version"] == "baseline1"
    assert [e["item"]["custom_name"] for e in body["entries"]] == ["D-1", "D-3", "D-5"]
    assert body["entries"][0]["reasons"] == [{"code": "expiry_dn", "n": 1, "text": "소비기한 D-1"}]

    rows = db.scalars(
        sa.select(Recommendation).where(Recommendation.recommendation_batch_id == body["batch_id"])
    ).all()
    assert sorted(r.rank for r in rows) == [1, 2, 3]
    assert {str(r.id) for r in rows} == {e["recommendation_id"] for e in body["entries"]}
    assert all(r.shown_at is None for r in rows)


def test_every_snapshot_passes_schema(
    api: TestClient, headers: dict[str, str], db: Session
) -> None:
    add(api, headers, "개봉", 9, opened_date=(seoul_today() - timedelta(days=1)).isoformat())
    add(api, headers, "기한없음", None, storage_type="FREEZER")
    add(api, headers, "D-2", 2)

    batch_id = api.post("/eat-first?limit=10", headers=headers).json()["batch_id"]
    rows = db.scalars(
        sa.select(Recommendation).where(Recommendation.recommendation_batch_id == batch_id)
    ).all()

    assert len(rows) == 3
    for row in rows:
        snapshot = FeatureSnapshotV1.model_validate(row.feature_snapshot)
        assert row.snapshot_schema_version == snapshot.snapshot_version == "1"
        assert snapshot.algorithm.rank == row.rank
        assert snapshot.algorithm.version == row.algorithm_version
        assert snapshot.context.inventory_active_count == 3
        assert str(snapshot.item.inventory_item_id) == str(row.inventory_item_id)
    opened = next(
        FeatureSnapshotV1.model_validate(r.feature_snapshot) for r in rows if r.rank == 1
    )
    assert opened.item.is_opened and opened.item.days_to_effective_date == 2


def test_shown_marks_exposure_once(api: TestClient, headers: dict[str, str], db: Session) -> None:
    add(api, headers, "D-1", 1)
    batch_id = api.post("/eat-first", headers=headers).json()["batch_id"]

    assert api.post(f"/eat-first/{batch_id}/shown", headers=headers).status_code == 204
    first = db.scalar(
        sa.select(Recommendation.shown_at).where(Recommendation.recommendation_batch_id == batch_id)
    )
    assert api.post(f"/eat-first/{batch_id}/shown", headers=headers).status_code == 204
    db.expire_all()
    second = db.scalar(
        sa.select(Recommendation.shown_at).where(Recommendation.recommendation_batch_id == batch_id)
    )

    assert first is not None and first == second


def test_shown_is_scoped_to_owner(api: TestClient, headers: dict[str, str]) -> None:
    add(api, headers, "D-1", 1)
    batch_id = api.post("/eat-first", headers=headers).json()["batch_id"]
    intruder = signup_headers(api)

    assert api.post(f"/eat-first/{batch_id}/shown", headers=intruder).status_code == 404


def test_excludes_finished_and_deleted_items(api: TestClient, headers: dict[str, str]) -> None:
    eaten = add(api, headers, "먹음", 1)
    deleted = add(api, headers, "삭제", 1)
    add(api, headers, "남음", 4)
    api.post(f"/inventory/{eaten}/actions", json={"action_type": "CONSUMED"}, headers=headers)
    api.delete(f"/inventory/{deleted}", headers=headers)

    names = [e["item"]["custom_name"] for e in api.post("/eat-first", headers=headers).json()["entries"]]

    assert names == ["남음"]


def test_action_can_reference_recommendation(api: TestClient, headers: dict[str, str]) -> None:
    item_id = add(api, headers, "D-1", 1)
    entry = api.post("/eat-first", headers=headers).json()["entries"][0]

    response = api.post(
        f"/inventory/{item_id}/actions",
        json={"action_type": "CONSUMED", "recommendation_id": entry["recommendation_id"]},
        headers=headers,
    )

    assert response.status_code == 201


def test_other_users_items_never_recommended(api: TestClient, headers: dict[str, str]) -> None:
    add(api, headers, "남의 것", 1)
    other = signup_headers(api)

    assert api.post("/eat-first", headers=other).json()["entries"] == []
