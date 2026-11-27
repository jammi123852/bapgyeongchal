"""재료 문자열 → 재료 이름 목록, 이름 정규화, 냉장고 음식 ↔ 재료 매칭 (stdlib only).

레시피 출처 두 가지가 같은 규칙을 쓴다:
    식약처 조리식품 레시피(COOKRCP01) 의 RCP_PARTS_DTLS
    유튜브 영상 설명란·올린 사람 댓글의 재료 목록

정규화 원칙 (한국어 복합명사는 뒤가 중심어):
    '다진 대파' → '대파', '무염버터' → '버터', '연두부' 는 그대로 두고 매칭 때 '두부' 와 뒤쪽 일치로 잇는다.
매칭: 같거나, 재료 이름이 냉장고 이름으로 끝나면(2글자 이상) 같은 재료로 본다.
    '두부' ↔ '연두부'·'순두부' O,  '파' ↔ '양파' X (1글자 제외),  '토마토' ↔ '방울토마토' O
"""

from __future__ import annotations

import re

# 거의 모든 집에 있어서 '더 필요한 재료' 에서 빼는 기본 양념
PANTRY = frozenset({
    "물", "소금", "설탕", "후추", "후춧가루", "간장", "진간장", "국간장", "참기름", "들기름", "식용유",
    "올리브유", "깨", "참깨", "통깨", "깨소금", "고춧가루", "식초", "맛술", "미림", "청주", "올리고당",
    "물엿", "요리당", "꿀", "다진마늘", "마늘", "생강", "다진생강", "고추장", "된장", "액젓", "멸치액젓",
    "까나리액젓", "굴소스", "전분", "녹말가루", "밀가루", "부침가루", "튀김가루", "버터", "마요네즈", "케첩",
    "매실액", "매실청", "소스",
})

# 같은 재료의 다른 이름 → 대표 이름
SYNONYMS = {
    "달걀": "계란", "계란노른자": "계란", "달걀노른자": "계란", "계란흰자": "계란", "달걀흰자": "계란",
    "메추리알": "메추리알", "다진마늘": "마늘", "깐마늘": "마늘", "통마늘": "마늘",
    "쪽파": "파", "실파": "파", "대파": "파", "파채": "파",
    "후춧가루": "후추", "진간장": "간장", "국간장": "간장", "저염간장": "간장",
    "통깨": "깨", "참깨": "깨", "깨소금": "깨",
    "청양고추": "고추", "홍고추": "고추", "풋고추": "고추",
    "우유팩": "우유",
}

# 앞에 붙는 손질·상태·제품 수식어 (띄어쓴 경우와 붙여쓴 경우 모두)
# 1글자 수식어('생'·'날'·'건'·'깐')는 넣지 않는다: '생크림'→'크림', '날치알'→'치알' 오류.
# '날콩가루'·'조선부추' 같은 경우는 매칭의 뒤쪽 일치가 처리한다.
MODIFIERS = (
    "다진", "저염", "무염", "조선", "칵테일", "냉동", "손질된", "손질한", "데친", "삶은", "볶은",
    "구운", "말린", "슬라이스", "채썬", "잘게썬", "불린", "익힌", "무가당", "저지방", "유기농",
)

_SECTION = re.compile(r"^\s*[●·•\-\[]?\s*[^,:：]{0,20}[:：]\s*")
_BRACKET = re.compile(r"[\(\[（［][^\)\]）］]*[\)\]）］]")  # (3/4모) [1인분]
_QUANTITY = re.compile(
    r"\d+(?:[.,/]\d+)?\s*(?:g|kg|ml|mL|l|L|cc|개|큰술|작은술|컵|쪽|장|줄기|마리|모|봉지|팩|캔|줌|대|알|톨|뿌리|포기|송이|조각|인분|T|t)?"
    r"|[½⅓⅔¼¾⅛]"
)
_AMOUNT_WORDS = re.compile(r"\s*(?:약간|적당량|조금|少々|취향껏|필요시|선택)\s*$")
_BULLET = re.compile(r"^[\s●·•\-\*✔✅▶▪︎◆◇■□○◎☆★♥#0-9.)]+")


def parse_ingredients(text: str) -> list[str]:
    """재료 문자열에서 재료 이름만 순서대로 뽑는다 (중복 제거, 원래 표기)."""
    lines = [ln.strip() for ln in text.replace("\r", "\n").split("\n") if ln.strip()]
    # 대부분의 줄에 수량이 있는 '정리된 목록'이면, 수량 없는 한 단어 줄은 제목·소제목이다 ('고명', '북엇국')
    structured = sum(bool(_QUANTITY.search(ln)) for ln in lines) * 2 >= len(lines)
    names: list[str] = []
    for line in lines:
        line = _BRACKET.sub(" ", line)  # 괄호 먼저: '(3/4모)' 의 '/' 로 쪼개지지 않게
        line = _SECTION.sub("", line) if re.search(r"[:：]", line) else line
        pieces = [p for p in re.split(r"[,，、/]|\s{2,}", line) if p.strip()]
        if structured and len(pieces) == 1 and not _QUANTITY.search(line):
            continue
        for piece in pieces:
            name = _QUANTITY.sub(" ", piece)
            name = _AMOUNT_WORDS.sub("", name)
            name = _BULLET.sub("", name)
            name = re.sub(r"\s+", " ", name).strip(" .·:-~")
            if 1 <= len(name) <= 15 and re.search(r"[가-힣A-Za-z]", name) and name not in names:
                names.append(name)
    return names


def normalize(name: str) -> str:
    """재료·음식 이름의 비교용 키: 공백 제거, 앞 수식어 제거, 동의어 통일."""
    key = re.sub(r"\s+", "", name.strip())
    changed = True
    while changed:
        changed = False
        for mod in MODIFIERS:
            if key.startswith(mod) and len(key) - len(mod) >= 1:
                key = key[len(mod):]
                changed = True
    return SYNONYMS.get(key, key)


def is_pantry(key: str) -> bool:
    return key in PANTRY or SYNONYMS.get(key, key) in {SYNONYMS.get(p, p) for p in PANTRY}


def same_ingredient(fridge_key: str, ingredient_key: str) -> bool:
    if not fridge_key or not ingredient_key:
        return False
    if fridge_key == ingredient_key:
        return True
    # 뒤쪽 일치: '두부' ↔ '연두부'. 1글자 이름('파')은 '양파' 같은 오탐이 커서 제외
    return len(fridge_key) >= 2 and ingredient_key.endswith(fridge_key)


def looks_like_title(name: str, recipe_name: str) -> bool:
    """RCP_PARTS_DTLS 첫 줄에 요리 이름이 재료처럼 섞여 들어오는 경우 ('새우두부계란찜')."""
    return re.sub(r"\s+", "", name) == re.sub(r"\s+", "", recipe_name)
