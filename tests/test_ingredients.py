"""재료 파서·정규화·매칭 (app/services/ingredients.py). DB 불필요."""

from __future__ import annotations

import pytest

from app.services.ingredients import is_pantry, looks_like_title, normalize, parse_ingredients, same_ingredient

# 식약처 COOKRCP01 실제 RCP_PARTS_DTLS (sample 키 응답, 2026-09-30)
SAMPLES = [
    ("새우 두부 계란찜",
     "새우두부계란찜\n연두부 75g(3/4모), 칵테일새우 20g(5마리), 달걀 30g(1/2개), 생크림 13g(1큰술), "
     "설탕 5g(1작은술), 무염버터 5g(1작은술)\n고명\n시금치 10g(3줄기)",
     ["연두부", "새우", "계란", "생크림", "설탕", "버터", "시금치"]),
    ("부추 콩가루 찜",
     "[1인분]조선부추 50g, 날콩가루 7g(1⅓작은술)\n·양념장 : 저염간장 3g(2/3작은술), 다진 대파 5g(1작은술), "
     "다진 마늘 2g(1/2쪽), 고춧가루 2g(1/3작은술), 요리당 2g(1/3작은술), 참기름 2g(1/3작은술), 참깨 약간",
     ["부추", "날콩가루", "간장", "파", "마늘", "고춧가루", "요리당", "참기름", "깨"]),
    ("방울토마토 소박이",
     "●방울토마토 소박이 : \n방울토마토 150g(5개), 양파 10g(3×1cm), 부추 10g(5줄기)\n●양념장 : \n"
     "고춧가루 4g(1작은술), 멸치액젓 3g(2/3작은술), 다진 마늘 2.5g(1/2쪽), 매실액 2g(1/3작은술), "
     "설탕 2g(1/3작은술), 물 2ml(1/3작은술), 통깨 약간",
     ["방울토마토", "양파", "부추", "고춧가루", "멸치액젓", "마늘", "매실액", "설탕", "물", "깨"]),
    ("순두부 사과 소스 오이무침",
     "●오이무침 :\n오이 70g(1/3개), 다진 땅콩 10g(1큰술)\n●순두부사과 소스 : \n순두부 40g(1/8봉지), 사과 50g(1/3개)",
     ["오이", "땅콩", "순두부", "사과"]),
    ("사과 새우 북엇국",
     "북엇국\n북어채 25g(15개), 새우 10g(3마리), 사과 30g(1/5개), 양파 40g(1/4개),\n표고버섯 20g(2장), 물 300ml(1½컵)",
     ["북어채", "새우", "사과", "양파", "표고버섯", "물"]),
]


@pytest.mark.parametrize(("recipe_name", "text", "expected"), SAMPLES, ids=[s[0] for s in SAMPLES])
def test_foodsafety_samples(recipe_name: str, text: str, expected: list[str]) -> None:
    names = [n for n in parse_ingredients(text) if not looks_like_title(n, recipe_name)]
    assert [normalize(n) for n in names] == expected


def test_youtube_style_list() -> None:
    text = "[재료]\n- 두부 1모\n- 대파 1/2대\n- 간장 2T\n- 설탕 1t\n\n구독과 좋아요 부탁드려요!!"
    keys = [normalize(n) for n in parse_ingredients(text)]
    assert keys[:4] == ["두부", "파", "간장", "설탕"]


def test_normalize_keeps_compound_food_names() -> None:
    assert normalize("생크림") == "생크림"  # '생' 을 수식어로 떼지 않는다
    assert normalize("다진 대파") == "파"
    assert normalize("달걀") == "계란"


@pytest.mark.parametrize(("fridge", "ingredient", "expected"), [
    ("두부", "연두부", True),
    ("두부", "순두부", True),
    ("토마토", "방울토마토", True),
    ("계란", "계란", True),
    ("파", "양파", False),  # 1글자는 뒤쪽 일치 안 함
    ("양파", "파", False),
    ("우유", "두유", False),
    ("", "두부", False),
])
def test_same_ingredient(fridge: str, ingredient: str, expected: bool) -> None:
    assert same_ingredient(normalize(fridge), normalize(ingredient)) is expected


def test_pantry() -> None:
    assert is_pantry(normalize("다진 마늘"))
    assert is_pantry(normalize("저염간장"))
    assert not is_pantry(normalize("두부"))
