"""소비기한 날짜 추출 규칙 단위 테스트 (DB 불필요)."""

from __future__ import annotations

from datetime import date

import pytest

from app.services.expiry_parse import find_dates, normalize_text, pick_expiry


@pytest.mark.parametrize(
    ("text", "expected", "precision"),
    [
        # 한국식
        ("2026.10.05까지", date(2026, 10, 5), "day"),
        ("2026. 10. 05", date(2026, 10, 5), "day"),
        ("소비기한: 2026년 10월 5일", date(2026, 10, 5), "day"),
        ("26.10.05", date(2026, 10, 5), "day"),
        # ExpDate 13종
        ("2021.08.03", date(2021, 8, 3), "day"),
        ("15.09.2024", date(2024, 9, 15), "day"),
        ("18/05/2021", date(2021, 5, 18), "day"),
        ("2021/08/05", date(2021, 8, 5), "day"),
        ("30 09 2021", date(2021, 9, 30), "day"),
        ("2021-11-30", date(2021, 11, 30), "day"),
        ("30-09-2021", date(2021, 9, 30), "day"),
        ("2021 11 30", date(2021, 11, 30), "day"),
        ("05/2022", date(2022, 5, 31), "month"),
        ("02.2023", date(2023, 2, 28), "month"),
        ("2022.04", date(2022, 4, 30), "month"),
        ("JUN 2023", date(2023, 6, 30), "month"),
        ("05 OCT 2026", date(2026, 10, 5), "day"),
    ],
)
def test_formats(text: str, expected: date, precision: str) -> None:
    found = find_dates(text)

    assert len(found) == 1, found
    assert found[0].value == expected
    assert found[0].precision == precision


def test_ocr_confusions_are_fixed() -> None:
    assert normalize_text("2O26.1O.O5") == "2026.10.05"
    assert find_dates("2O26.l0.05")[0].value == date(2026, 10, 5)


def test_invalid_dates_are_ignored() -> None:
    assert find_dates("2026.13.05") == []
    assert find_dates("2026.02.30") == []
    assert find_dates("1999.10.05") == []


def test_ambiguous_day_month_is_flagged() -> None:
    (c,) = find_dates("05/10/2026")
    assert c.value == date(2026, 10, 5)  # DMY 우선
    assert c.ambiguous

    (unambiguous,) = find_dates("25/10/2026")
    assert not unambiguous.ambiguous


def test_keyword_wins_over_later_date() -> None:
    lines = ["제조일자 2026.09.01", "2026.12.31 LOT", "소비기한 2026.10.05"]

    assert pick_expiry(lines).value == date(2026, 10, 5)


def test_without_keyword_latest_date_wins() -> None:
    """제조일은 소비기한보다 앞서므로 가장 늦은 날짜."""
    assert pick_expiry(["2026.09.01", "2026.10.05"]).value == date(2026, 10, 5)


def test_day_precision_beats_month_precision() -> None:
    assert pick_expiry(["10/2026", "2026.09.20"]).value == date(2026, 9, 20)


def test_numbers_that_are_not_dates() -> None:
    assert pick_expiry(["8B제조(09:39)", "080-940-3333", "355 kcal"]) is None


def test_real_example_from_expdate() -> None:
    """ExpDate test_00327: 삼양 컵라면 바닥 인쇄."""
    assert pick_expiry(["2021.05.19까지", "8B제조(09:39)"]).value == date(2021, 5, 19)


def test_date_split_across_lines() -> None:
    assert pick_expiry(["EXP:2022.", "04.04"]).value == date(2022, 4, 4)
