"""임박 재료 요리 추천 (GET /recipes/suggest).

확인: 임박(오늘~D-3) 재료가 든 요리만 / 기한 지난 음식은 재료로 안 씀 / 순위 규칙 /
기본 양념은 '더 필요' 에서 제외 / 다른 사용자 냉장고는 안 봄 / 유튜브는 영상 주소와 출처.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import RecipeSource
from app.models import Recipe
from app.services.recipes import build_ingredients
from tests.conftest import signup_headers


def local_today() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def add_recipe(db: Session, name: str, ingredients: list[str], source: RecipeSource = RecipeSource.FOODSAFETY,
               external_id: str | None = None) -> Recipe:
    recipe = Recipe(source=source, external_id=external_id or uuid.uuid4().hex, name=name,
                    ingredients=build_ingredients(ingredients), steps=["1. 만든다."] if source == RecipeSource.FOODSAFETY else None,
                    fetched_at=datetime.now(UTC))
    db.add(recipe)
    db.flush()
    return recipe


def add_item(api: TestClient, headers: dict[str, str], name: str, days: int | None) -> None:
    body: dict[str, object] = {"custom_name": name}
    if days is not None:
        body["expiry_date"] = (local_today() + timedelta(days=days)).isoformat()
    response = api.post("/inventory", json=body, headers=headers)
    assert response.status_code == 201, response.text


def suggest(api: TestClient, headers: dict[str, str]) -> list[dict]:
    response = api.get("/recipes/suggest", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_requires_auth(api: TestClient) -> None:
    assert api.get("/recipes/suggest").status_code == 401


def test_only_recipes_with_urgent_items(api: TestClient, db: Session) -> None:
    add_recipe(db, "두부조림", ["두부", "간장", "대파"])
    add_recipe(db, "감자볶음", ["감자", "소금"])
    headers = signup_headers(api)
    add_item(api, headers, "두부", 2)
    add_item(api, headers, "감자", 20)  # 임박 아님
    names = [s["name"] for s in suggest(api, headers)]
    assert names == ["두부조림"]


def test_no_urgent_items_returns_empty(api: TestClient, db: Session) -> None:
    add_recipe(db, "두부조림", ["두부", "간장"])
    headers = signup_headers(api)
    add_item(api, headers, "두부", 10)
    assert suggest(api, headers) == []


def test_expired_item_not_used(api: TestClient, db: Session) -> None:
    add_recipe(db, "두부조림", ["두부", "간장"])
    headers = signup_headers(api)
    add_item(api, headers, "두부", -1)
    assert suggest(api, headers) == []


def test_ranking_and_missing(api: TestClient, db: Session) -> None:
    add_recipe(db, "두부계란찜", ["연두부", "달걀", "시금치", "소금"])
    add_recipe(db, "두부조림", ["두부", "간장", "대파"])
    add_recipe(db, "계란말이", ["계란", "대파", "당근", "소금"])
    headers = signup_headers(api)
    add_item(api, headers, "두부", 1)
    add_item(api, headers, "계란", 3)
    add_item(api, headers, "대파", 30)
    result = suggest(api, headers)
    # 두부계란찜: 임박 2개 → 1위.
    # 두부조림·계란말이: 임박 1개 + 대파 = 냉장고 재료 2개로 동률 → 더 필요한 재료 0개(두부조림) < 1개(당근)
    assert [s["name"] for s in result] == ["두부계란찜", "두부조림", "계란말이"]
    first = result[0]
    assert {u["name"] for u in first["uses"]} == {"두부", "계란"}
    assert first["missing"] == ["시금치"]  # 소금은 기본 양념이라 제외
    assert result[1]["missing"] == []
    assert result[2]["missing"] == ["당근"]


def test_other_users_fridge_ignored(api: TestClient, db: Session) -> None:
    add_recipe(db, "두부조림", ["두부", "간장"])
    owner = signup_headers(api)
    add_item(api, owner, "두부", 1)
    other = signup_headers(api)
    assert suggest(api, other) == []


def test_youtube_recipe_has_url_and_attribution(api: TestClient, db: Session) -> None:
    add_recipe(db, "백종원 두부조림", ["두부", "간장"], RecipeSource.YOUTUBE, external_id="abcDEF12345")
    headers = signup_headers(api)
    add_item(api, headers, "두부", 0)
    [s] = suggest(api, headers)
    assert s["source"] == "YOUTUBE"
    assert s["url"] == "https://www.youtube.com/watch?v=abcDEF12345"
    assert s["video_id"] == "abcDEF12345"
    assert s["steps"] is None
    assert s["attribution"] == "YouTube"
