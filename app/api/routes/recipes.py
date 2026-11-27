"""임박 재료 요리 추천 라우트."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.enums import RecipeSource
from app.db.session import get_db
from app.models import User
from app.schemas.recipes import RecipeSuggestion, RecipeUse
from app.services.recipes import suggest

router = APIRouter(prefix="/recipes", tags=["recipes"])

ATTRIBUTION = {
    RecipeSource.FOODSAFETY: "식품의약품안전처 식품안전나라 조리식품 레시피",
    RecipeSource.YOUTUBE: "YouTube",
}


@router.get("/suggest", response_model=list[RecipeSuggestion])
def suggest_recipes(
    limit: int = Query(default=5, ge=1, le=20),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RecipeSuggestion]:
    """곧 기한이 끝나는 냉장고 음식이 들어가는 요리. 임박 음식이 없으면 빈 목록."""
    out = []
    for s in suggest(db, user, limit):
        recipe = s.recipe
        is_youtube = recipe.source == RecipeSource.YOUTUBE
        out.append(RecipeSuggestion(
            recipe_id=recipe.id,
            source=recipe.source,
            name=recipe.name,
            category=recipe.category,
            image_url=recipe.image_url,
            url=f"https://www.youtube.com/watch?v={recipe.external_id}" if is_youtube else None,
            video_id=recipe.external_id if is_youtube else None,
            channel_title=recipe.channel_title,
            steps=recipe.steps,
            uses=[RecipeUse(item_id=u.item.id, name=u.item.custom_name, days_left=u.days_left, urgent=u.urgent)
                  for u in s.uses],
            missing=s.missing,
            attribution=ATTRIBUTION[recipe.source],
        ))
    return out
