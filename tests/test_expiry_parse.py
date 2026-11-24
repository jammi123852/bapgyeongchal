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


# --- train 분할 오류 분석(2026-09-29)에서 찾은 OCR 변형 ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("BESTBY 20210702", date(2021, 7, 2)),  # 붙여 쓴 날짜
        ("2020.12.091XI", date(2020, 12, 9)),  # '까지' → '1XI'
        ("023.02.197XI", date(2023, 2, 19)),  # 연도 첫 자리 누락 + '까지' → '7XI'
        ("202107.15J", date(2021, 7, 15)),  # 점 누락
        ("29N0V2021 PV 03:26", date(2021, 11, 29)),  # NOV 의 O → 0
    ],
)
def test_ocr_variants(text: str, expected: date) -> None:
    assert pick_expiry([text]).value == expected


def test_kkaji_misread_counts_as_keyword() -> None:
    (c,) = find_dates("2020.12.091XI")
    assert c.near_keyword


def test_eight_digit_lot_numbers_are_not_dates() -> None:
    assert find_dates("20123521") == []  # 35월
    assert find_dates("8801391102715") == []  # 바코드
    assert find_dates("20083617") == []


def test_date_split_into_two_lines_with_dots() -> None:
    assert pick_expiry(["2021.06.", ".28.", "F", "10:33"]).value == date(2021, 6, 28)


def test_line_join_not_used_when_a_full_date_exists() -> None:
    assert pick_expiry(["2021.06.28", "2021.06.", ".30"]).value == date(2021, 6, 28)


# --- 여러 해석 + 말이 되는 날짜 고르기 (2026-09-30) ---


@pytest.mark.parametrize(
    ("text", "expected", "alternative"),
    [
        ("04-11-23", date(2023, 11, 4), date(2004, 11, 23)),  # 2004년은 말이 안 됨 → 일/월/연
        ("11/08/23", date(2023, 8, 11), date(2011, 8, 23)),
        ("21.12.22", date(2022, 12, 21), date(2021, 12, 22)),  # 둘 다 가능 → 일/월/연 우선, 연/월/일은 대안
    ],
)
def test_two_digit_year_interpretations(text: str, expected: date, alternative: date) -> None:
    (c,) = find_dates(text)
    assert c.value == expected
    assert c.ambiguous
    assert alternative in c.alternatives


def test_korean_yymmdd_wins_when_dmy_is_implausible() -> None:
    (c,) = find_dates("26.10.05")  # 일/월/연이면 2005년 → 말이 안 됨
    assert c.value == date(2026, 10, 5)


def test_reference_date_decides_plausibility() -> None:
    today = date(2026, 9, 30)
    (c,) = find_dates("21.12.30", today)  # 일/월/연 2030-12-21, 연/월/일 2021-12-30 둘 다 창 안
    assert c.value == date(2030, 12, 21)
    assert date(2021, 12, 30) in c.alternatives


def test_unambiguous_date_has_no_alternatives() -> None:
    (c,) = find_dates("2026.10.05")
    assert c.alternatives == () and not c.ambiguous


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("22/MAY/2023", date(2023, 5, 22)),
        ("11/OCT/2021", date(2021, 10, 11)),
        ("2021 JUN 12", date(2021, 6, 12)),
        ("MAY 22 2023", date(2023, 5, 22)),
        ("15 FEB 22", date(2022, 2, 15)),
    ],
)
def test_month_name_with_separators(text: str, expected: date) -> None:
    assert pick_expiry([text]).value == expected


def test_implausible_date_loses_to_plausible_one() -> None:
    assert pick_expiry(["1999.01.01", "2026.10.05"]).value == date(2026, 10, 5)
