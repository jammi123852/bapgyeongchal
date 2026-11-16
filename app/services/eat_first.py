"""Eat-First 추천 (docs/mvp-v0_1-freeze.md 9절).

baseline0: 소비기한 오름차순. 모든 개선의 비교 기준선(대조군).
baseline1: baseline0 + '개봉하면 실질 기한이 앞당겨진다' 한 가지 개념만 추가.
    effective_date = min(expiry_date, opened_date + OPEN_LIFE_DAYS)

하지 않는 것: 가중치 점수 합산, 식품군별 계수, 보관위치·수량·구매빈도 반영 (근거 없음).

score 는 '실질 기한까지 남은 일수'다 (작을수록 먼저). 기한 정보가 없으면 NO_DATE_SCORE.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from app.models import InventoryItem

OPEN_LIFE_DAYS = 3
NO_DATE_SCORE = Decimal("99999")


class Algorithm(str, Enum):
    BASELINE0 = "baseline0"
    BASELINE1 = "baseline1"


# --- 이유 코드와 UI 문구 (1:1, 템플릿에서만 생성) ---

REASON_TEMPLATES: dict[str, str] = {
    "expiry_passed": "소비기한이 지났어요. 상태를 확인해 주세요",
    "expiry_d0": "오늘까지예요",
    "expiry_dn": "소비기한 D-{n}",
    "opened_n_days": "개봉한 지 {n}일 됐어요",
    "no_expiry": "소비기한이 등록되지 않았어요",
}
# opened_n_days 의 n=0 표기 ("개봉한 지 0일" 대신)
OPENED_TODAY_TEXT = "오늘 개봉했어요"

# 판정·지시로 읽힐 수 있는 표현. 문구에 들어가면 안 된다 (안전 게이트).
FORBIDDEN_WORDS = ("상했", "안전", "버리세요", "위험", "식중독")


@dataclass(frozen=True)
class Reason:
    code: str
    n: int | None = None

    @property
    def text(self) -> str:
        if self.code == "opened_n_days" and self.n == 0:
            return OPENED_TODAY_TEXT
        return REASON_TEMPLATES[self.code].format(n=self.n)

    def as_json(self) -> dict[str, object]:
        return {"code": self.code} if self.n is None else {"code": self.code, "n": self.n}


@dataclass
class Ranked:
    item: InventoryItem
    rank: int
    score: Decimal
    effective_date: date | None
    reasons: list[Reason] = field(default_factory=list)


def expiry_reason(expiry_date: date, today: date) -> Reason:
    days = (expiry_date - today).days
    if days < 0:
        return Reason("expiry_passed")
    if days == 0:
        return Reason("expiry_d0")
    return Reason("expiry_dn", days)


def _created_key(item: InventoryItem) -> tuple:
    return (item.created_at, str(item.id))


def _rank_baseline0(items: Sequence[InventoryItem], today: date) -> list[Ranked]:
    def sort_key(item: InventoryItem) -> tuple:
        has_date = item.expiry_date is not None
        return (not has_date, item.expiry_date or date.max, *_created_key(item))

    ranked = []
    for item in sorted(items, key=sort_key):
        if item.expiry_date is None:
            ranked.append(Ranked(item, 0, NO_DATE_SCORE, None, [Reason("no_expiry")]))
        else:
            score = Decimal((item.expiry_date - today).days)
            ranked.append(
                Ranked(item, 0, score, item.expiry_date, [expiry_reason(item.expiry_date, today)])
            )
    return ranked


def effective_date_baseline1(item: InventoryItem) -> date | None:
    candidates = [d for d in (item.expiry_date, _open_limit(item)) if d is not None]
    return min(candidates) if candidates else None


def _open_limit(item: InventoryItem) -> date | None:
    if item.opened_date is None:
        return None
    return item.opened_date + timedelta(days=OPEN_LIFE_DAYS)


def _reasons_baseline1(item: InventoryItem, today: date) -> list[Reason]:
    """정렬에 실제로 쓰인 근거를 먼저 둔다 (reasons 와 정렬 근거 일치)."""
    open_limit = _open_limit(item)
    opened_reason = (
        Reason("opened_n_days", (today - item.opened_date).days)
        if item.opened_date is not None
        else None
    )
    if item.expiry_date is None:
        if opened_reason is not None:
            return [opened_reason, Reason("no_expiry")]
        return [Reason("no_expiry")]

    by_expiry = expiry_reason(item.expiry_date, today)
    if open_limit is not None and open_limit < item.expiry_date:
        assert opened_reason is not None
        return [opened_reason, by_expiry]
    if opened_reason is not None:
        return [by_expiry, opened_reason]
    return [by_expiry]


def _rank_baseline1(items: Sequence[InventoryItem], today: date) -> list[Ranked]:
    def sort_key(item: InventoryItem) -> tuple:
        effective = effective_date_baseline1(item)
        return (
            effective is None,
            effective or date.max,
            item.opened_date is None,  # tie-break 1: 개봉한 것 우선
            *_created_key(item),  # tie-break 2: 오래 방치된 것 우선
        )

    ranked = []
    for item in sorted(items, key=sort_key):
        effective = effective_date_baseline1(item)
        score = NO_DATE_SCORE if effective is None else Decimal((effective - today).days)
        ranked.append(Ranked(item, 0, score, effective, _reasons_baseline1(item, today)))
    return ranked


RANKERS: dict[Algorithm, Callable[[Sequence[InventoryItem], date], list[Ranked]]] = {
    Algorithm.BASELINE0: _rank_baseline0,
    Algorithm.BASELINE1: _rank_baseline1,
}


def rank_items(
    items: Sequence[InventoryItem], today: date, algorithm: Algorithm
) -> list[Ranked]:
    """활성 재고 전체를 순위화한다. rank 는 1부터."""
    ranked = RANKERS[algorithm](items, today)
    for index, entry in enumerate(ranked, start=1):
        entry.rank = index
    return ranked
