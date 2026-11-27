"""임박 재료 요리 추천.

임박 = Eat-First 실질 기한(baseline1: 소비기한과 개봉 후 3일 중 이른 날)이 오늘 ~ URGENT_DAYS 일 뒤.
기한이 이미 지난 음식은 요리 재료로 추천하지 않는다 (안전 표현 원칙: 먹어도 된다는 신호를 주지 않는다).

순위 (근거 없는 가중치 합산 대신 사전식 비교):
    1) 들어가는 임박 재료 수 많은 것  2) 냉장고 재료 수 많은 것
    3) 더 사야 하는 재료(기본 양념 제외) 적은 것  4) 가장 급한 재료의 남은 일수 적은 것
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.enums import InventoryStatus
from app.db.base import not_deleted
from app.models import InventoryItem, Recipe, User
from app.services.eat_first import effective_date_baseline1
from app.services.ingredients import is_pantry, normalize, same_ingredient

URGENT_DAYS = 3


def build_ingredients(names: Sequence[str]) -> list[dict[str, Any]]:
    """레시피 저장용 재료 목록 (정규화 키가 같은 재료는 한 번만)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for name in names:
        key = normalize(name)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "key": key, "pantry": is_pantry(key)})
    return out


@dataclass(frozen=True)
class FridgeUse:
    item: InventoryItem
    days_left: int | None  # None = 기한 정보 없음
    urgent: bool


@dataclass(frozen=True)
class Suggestion:
    recipe: Recipe
    uses: list[FridgeUse]
    missing: list[str]  # 더 필요한 재료 (기본 양념 제외, 원래 표기)

    @property
    def urgent_count(self) -> int:
        return sum(u.urgent for u in self.uses)


def _fridge(items: Sequence[InventoryItem], today: date) -> list[tuple[InventoryItem, str, int | None]]:
    out = []
    for item in items:
        effective = effective_date_baseline1(item)
        days = None if effective is None else (effective - today).days
        if days is not None and days < 0:
            continue  # 기한 지난 것은 재료로 쓰지 않는다
        out.append((item, normalize(item.custom_name), days))
    return out


def match_recipe(recipe: Recipe, fridge: list[tuple[InventoryItem, str, int | None]]) -> Suggestion:
    uses: list[FridgeUse] = []
    used_items: set[Any] = set()
    missing: list[str] = []
    for ingredient in recipe.ingredients:
        hit = next(
            ((item, days) for item, key, days in fridge
             if item.id not in used_items and same_ingredient(key, ingredient["key"])),
            None,
        )
        if hit is not None:
            item, days = hit
            used_items.add(item.id)
            uses.append(FridgeUse(item, days, days is not None and days <= URGENT_DAYS))
        elif not ingredient.get("pantry"):
            missing.append(ingredient["name"])
    return Suggestion(recipe, uses, missing)


def rank(recipes: Sequence[Recipe], items: Sequence[InventoryItem], today: date, limit: int) -> list[Suggestion]:
    fridge = _fridge(items, today)
    if not any(days is not None and days <= URGENT_DAYS for _, _, days in fridge):
        return []
    candidates = [s for s in (match_recipe(r, fridge) for r in recipes) if s.urgent_count > 0]
    candidates.sort(key=lambda s: (
        -s.urgent_count,
        -len(s.uses),
        len(s.missing),
        min(u.days_left for u in s.uses if u.urgent),
        s.recipe.name,
    ))
    return candidates[:limit]


def suggest(db: Session, user: User, limit: int, now: datetime | None = None) -> list[Suggestion]:
    today = (now or datetime.now(UTC)).astimezone(ZoneInfo(user.timezone)).date()
    items = list(db.scalars(sa.select(InventoryItem).where(
        InventoryItem.user_id == user.id,
        InventoryItem.status == InventoryStatus.ACTIVE,
        not_deleted(InventoryItem),
    )))
    recipes = list(db.scalars(sa.select(Recipe)))
    return rank(recipes, items, today, limit)
