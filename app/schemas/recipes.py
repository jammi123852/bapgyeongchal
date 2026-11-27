"""임박 재료 요리 추천 응답."""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from app.core.enums import RecipeSource


class RecipeUse(BaseModel):
    item_id: uuid.UUID
    name: str
    days_left: int | None
    urgent: bool


class RecipeSuggestion(BaseModel):
    recipe_id: uuid.UUID
    source: RecipeSource
    name: str
    category: str | None
    image_url: str | None
    url: str | None  # 유튜브 영상 주소 (식약처는 None)
    video_id: str | None
    channel_title: str | None
    steps: list[str] | None
    uses: list[RecipeUse]
    missing: list[str]
    attribution: str
