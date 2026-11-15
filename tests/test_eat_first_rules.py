"""Eat-First 정렬 규칙 단위 테스트 (Step 6, 8). DB 를 쓰지 않는다."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import InventoryItem
from app.services.eat_first import (
    FORBIDDEN_WORDS,
    REASON_TEMPLATES,
    Algorithm,
    Reason,
    effective_date_baseline1,
    rank_items,
)

TODAY = date(2026, 10, 1)
T0 = datetime(2026, 9, 1, tzinfo=UTC)


def item(
    name: str,
    expiry: date | None = None,
    opened: date | None = None,
    created_offset_min: int = 0,
) -> InventoryItem:
    return InventoryItem(
        id=uuid.uuid4(),
        custom_name=name,
        expiry_date=expiry,
        opened_date=opened,
        created_at=T0 + timedelta(minutes=created_offset_min),
    )


def names(items: list[InventoryItem], algorithm: Algorithm) -> list[str]:
    return [r.item.custom_name for r in rank_items(items, TODAY, algorithm)]


# --- baseline0 ---


def test_baseline0_sorts_by_expiry_and_puts_missing_last() -> None:
    items = [
        item("없음A", created_offset_min=1),
        item("10일", TODAY + timedelta(days=10)),
        item("지남", TODAY - timedelta(days=1)),
        item("없음B", created_offset_min=2),
        item("오늘", TODAY),
    ]

    assert names(items, Algorithm.BASELINE0) == ["지남", "오늘", "10일", "없음A", "없음B"]


def test_baseline0_same_expiry_older_first() -> None:
    items = [item("새것", TODAY, created_offset_min=5), item("옛것", TODAY, created_offset_min=1)]

    assert names(items, Algorithm.BASELINE0) == ["옛것", "새것"]


def test_baseline0_ignores_opened_date() -> None:
    items = [
        item("미개봉", TODAY + timedelta(days=2)),
        item("개봉", TODAY + timedelta(days=9), opened=TODAY - timedelta(days=5)),
    ]

    assert names(items, Algorithm.BASELINE0) == ["미개봉", "개봉"]


def test_ranks_start_at_one_and_are_consecutive() -> None:
    items = [item(str(i), TODAY + timedelta(days=i)) for i in range(4)]

    assert [r.rank for r in rank_items(items, TODAY, Algorithm.BASELINE0)] == [1, 2, 3, 4]


def test_empty_inventory() -> None:
    assert rank_items([], TODAY, Algorithm.BASELINE1) == []


# --- baseline1 ---


def test_baseline1_opening_pulls_item_forward() -> None:
    items = [
        item("미개봉 D-2", TODAY + timedelta(days=2)),
        # 개봉 2일 전 → 실질 기한 = 개봉+3 = 내일
        item("개봉 D-9", TODAY + timedelta(days=9), opened=TODAY - timedelta(days=2)),
    ]

    assert names(items, Algorithm.BASELINE1) == ["개봉 D-9", "미개봉 D-2"]


def test_baseline1_effective_date_is_min() -> None:
    early = item("x", TODAY + timedelta(days=1), opened=TODAY)
    late = item("y", TODAY + timedelta(days=10), opened=TODAY)

    assert effective_date_baseline1(early) == TODAY + timedelta(days=1)
    assert effective_date_baseline1(late) == TODAY + timedelta(days=3)


def test_baseline1_tie_prefers_opened_then_older() -> None:
    same = TODAY + timedelta(days=3)
    items = [
        item("미개봉 옛것", same, created_offset_min=0),
        item("개봉", same + timedelta(days=5), opened=TODAY, created_offset_min=9),
        item("미개봉 새것", same, created_offset_min=5),
    ]

    assert names(items, Algorithm.BASELINE1) == ["개봉", "미개봉 옛것", "미개봉 새것"]


def test_baseline1_opened_without_expiry_is_ranked_by_open_limit() -> None:
    items = [
        item("기한없음"),
        item("개봉만", opened=TODAY - timedelta(days=1)),  # 실질 기한 D-2
        item("D-5", TODAY + timedelta(days=5)),
    ]

    assert names(items, Algorithm.BASELINE1) == ["개봉만", "D-5", "기한없음"]


# --- reasons (Step 8) ---


def reasons_of(entry_item: InventoryItem, algorithm: Algorithm = Algorithm.BASELINE1) -> list[Reason]:
    return rank_items([entry_item], TODAY, algorithm)[0].reasons


@pytest.mark.parametrize(
    ("expiry", "expected"),
    [
        (TODAY - timedelta(days=2), Reason("expiry_passed")),
        (TODAY, Reason("expiry_d0")),
        (TODAY + timedelta(days=4), Reason("expiry_dn", 4)),
    ],
)
def test_expiry_reasons(expiry: date, expected: Reason) -> None:
    assert reasons_of(item("x", expiry)) == [expected]


def test_no_expiry_reason() -> None:
    assert reasons_of(item("x")) == [Reason("no_expiry")]


def test_reason_order_follows_sort_basis() -> None:
    """정렬을 결정한 근거가 첫 번째 이유다."""
    open_binding = item("a", TODAY + timedelta(days=9), opened=TODAY - timedelta(days=2))
    expiry_binding = item("b", TODAY + timedelta(days=1), opened=TODAY)

    assert reasons_of(open_binding)[0] == Reason("opened_n_days", 2)
    assert reasons_of(expiry_binding)[0] == Reason("expiry_dn", 1)


def test_first_reason_matches_score() -> None:
    """이유가 말하는 날짜와 정렬 점수(실질 기한까지 일수)가 모순되지 않는다."""
    cases = [
        item("a", TODAY + timedelta(days=9), opened=TODAY - timedelta(days=2)),
        item("b", TODAY + timedelta(days=1), opened=TODAY),
        item("c", TODAY + timedelta(days=6)),
    ]
    for entry in rank_items(cases, TODAY, Algorithm.BASELINE1):
        first = entry.reasons[0]
        if first.code == "expiry_dn":
            assert entry.score == first.n
        elif first.code == "opened_n_days":
            assert first.n is not None
            assert entry.score == 3 - first.n


def test_baseline0_never_uses_opened_reason() -> None:
    reasons = reasons_of(
        item("x", TODAY + timedelta(days=9), opened=TODAY - timedelta(days=2)), Algorithm.BASELINE0
    )

    assert [r.code for r in reasons] == ["expiry_dn"]


def test_reason_texts_contain_no_forbidden_words() -> None:
    """안전 게이트: 상함·안전 판정이나 폐기 지시로 읽히는 문구 금지."""
    rendered = [template.format(n=3) for template in REASON_TEMPLATES.values()]
    for text in rendered:
        for word in FORBIDDEN_WORDS:
            assert word not in text, f"금지어 '{word}' 포함: {text}"


def test_reason_text_rendering() -> None:
    assert Reason("expiry_dn", 2).text == "소비기한 D-2"
    assert Reason("opened_n_days", 3).text == "개봉한 지 3일 됐어요"
