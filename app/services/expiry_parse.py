"""OCR 텍스트에서 소비기한 날짜 후보를 찾는다 (표준 라이브러리만 사용).

OCR 엔진(별도 venv)과 백엔드 양쪽에서 import 하므로 app 의 다른 모듈에 의존하지 않는다.

원칙:
- 결과는 '후보'다. 앱은 항상 사용자 확인 후 저장한다 (자동 확정 금지).
- 월까지만 있는 표기(05/2022, JUN 2023)는 그 달 말일로 두고 precision='month' 로 표시한다.
- 여러 날짜가 있으면 소비기한 키워드(까지·소비기한·EXP 등) 근처 → 가장 늦은 날짜 순으로 고른다
  (제조일은 소비기한보다 앞선다).

지원 형식 (ExpDate 13종 + 한국식):
  2026.10.05 / 2026-10-05 / 2026/10/05 / 2026 10 05 / 2026. 10. 05 / 2026년 10월 5일
  26.10.05 (한국식 YY.MM.DD) / 05.10.2026 / 05/10/2026 / 05-10-2026 / 05 10 2026 / 05/10/26
  10.2026 / 10/2026 / 2026.10 / OCT 2026 / 05 OCT 2026
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

KEYWORDS = (
    "까지",
    "소비기한",
    "유통기한",
    "품질유지기한",
    "EXP",
    "BEST BEFORE",
    "BEST BY",
    "USE BY",
    "BB",
)

MONTHS = {
    m: i
    for i, names in enumerate(
        [
            (),
            ("JAN",),
            ("FEB",),
            ("MAR",),
            ("APR",),
            ("MAY",),
            ("JUN",),
            ("JUL",),
            ("AUG",),
            ("SEP", "SEPT"),
            ("OCT",),
            ("NOV",),
            ("DEC",),
        ]
    )
    for m in names
}

YEAR_MIN, YEAR_MAX = 2000, 2099

_SEP = r"\s*[./\-\s]\s*"
# 순서 중요: 긴(구체적) 패턴을 먼저 시도한다.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Y년M월D일", re.compile(r"(?P<y>\d{4})\s*년\s*(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일")),
    ("YMD", re.compile(rf"(?<!\d)(?P<y>\d{{4}}){_SEP}(?P<m>\d{{1,2}}){_SEP}(?P<d>\d{{1,2}})(?!\d)")),
    ("DMY", re.compile(rf"(?<!\d)(?P<d>\d{{1,2}}){_SEP}(?P<m>\d{{1,2}}){_SEP}(?P<y>\d{{4}})(?!\d)")),
    ("D MON Y", re.compile(r"(?<![A-Z\d])(?P<d>\d{1,2})\s*(?P<mon>[A-Z]{3,4})\s*(?P<y>\d{4}|\d{2})(?!\d)")),
    ("MON Y", re.compile(r"(?<![A-Z])(?P<mon>[A-Z]{3,4})[\s./\-]*(?P<y>\d{4})(?!\d)")),
    ("AA.BB.CC", re.compile(rf"(?<!\d)(?P<a>\d{{2}}){_SEP}(?P<b>\d{{2}}){_SEP}(?P<c>\d{{2}})(?!\d)")),
    # 월 뒤에 숫자가 더 이어지면(잘못된 연월일의 일부) 연-월 로 보지 않는다.
    ("YM", re.compile(r"(?<!\d)(?P<y>\d{4})\s*[./\-]\s*(?P<m>\d{1,2})(?!\d)(?!\s*[./\-]\s*\d)")),
    ("MY", re.compile(r"(?<!\d)(?<!\d[./\-])(?P<m>\d{1,2})\s*[./\-]\s*(?P<y>\d{4})(?!\d)")),
]


@dataclass(frozen=True)
class DateCandidate:
    value: date
    precision: str  # 'day' | 'month'
    raw: str
    pattern: str
    near_keyword: bool
    ambiguous: bool  # 일/월 또는 연도 위치 해석이 둘 이상 가능했음


def _valid(y: int, m: int, d: int) -> date | None:
    if not (YEAR_MIN <= y <= YEAR_MAX and 1 <= m <= 12):
        return None
    if not 1 <= d <= calendar.monthrange(y, m)[1]:
        return None
    return date(y, m, d)


def _month_end(y: int, m: int) -> date | None:
    if not (YEAR_MIN <= y <= YEAR_MAX and 1 <= m <= 12):
        return None
    return date(y, m, calendar.monthrange(y, m)[1])


def _two_digit_year(yy: int) -> int:
    return 2000 + yy


def normalize_text(text: str) -> str:
    """OCR 에서 흔한 혼동을 정리한다. 숫자 사이의 O→0, I/l→1, 쉼표→점, 콜론 제거."""
    t = text.upper().replace(",", ".").replace("·", ".")
    t = re.sub(r"(?<=\d)[OQ](?=\d)|(?<=\d)[OQ](?=[./\-])|(?<=[./\-])[OQ](?=\d)", "0", t)
    t = re.sub(r"(?<=\d)[IL|](?=\d)|(?<=[./\-])[IL|](?=\d)|(?<=\d)[IL|](?=[./\-])", "1", t)
    return t


def _has_keyword(text: str, start: int, end: int, window: int = 12) -> bool:
    around = text[max(0, start - window) : end + window]
    return any(k in around for k in KEYWORDS)


def _from_match(name: str, m: re.Match[str], text: str) -> list[DateCandidate]:
    g = m.groupdict()
    near = _has_keyword(text, m.start(), m.end())
    raw = m.group(0).strip()

    def cand(value: date | None, precision: str = "day", ambiguous: bool = False) -> list[DateCandidate]:
        return [] if value is None else [DateCandidate(value, precision, raw, name, near, ambiguous)]

    if name in ("Y년M월D일", "YMD"):
        return cand(_valid(int(g["y"]), int(g["m"]), int(g["d"])))
    if name == "DMY":
        d, mth, y = int(g["d"]), int(g["m"]), int(g["y"])
        dmy = _valid(y, mth, d)
        mdy = _valid(y, d, mth)
        if dmy and mdy and dmy != mdy:
            return cand(dmy, ambiguous=True)  # 일/월 둘 다 12 이하 → DMY 우선, 확인 필요 표시
        return cand(dmy or mdy)
    if name == "D MON Y":
        mon = MONTHS.get(g["mon"])
        if mon is None:
            return []
        y = int(g["y"]) if len(g["y"]) == 4 else _two_digit_year(int(g["y"]))
        return cand(_valid(y, mon, int(g["d"])))
    if name == "MON Y":
        mon = MONTHS.get(g["mon"])
        return [] if mon is None else cand(_month_end(int(g["y"]), mon), "month")
    if name == "AA.BB.CC":
        a, b, c = int(g["a"]), int(g["b"]), int(g["c"])
        ymd = _valid(_two_digit_year(a), b, c)  # 한국식 26.10.05
        dmy = _valid(_two_digit_year(c), b, a)  # 유럽식 05.10.26
        if ymd and dmy and ymd != dmy:
            return cand(ymd, ambiguous=True)
        return cand(ymd or dmy)
    if name == "YM":
        return cand(_month_end(int(g["y"]), int(g["m"])), "month")
    if name == "MY":
        return cand(_month_end(int(g["y"]), int(g["m"])), "month")
    return []


def find_dates(text: str) -> list[DateCandidate]:
    """텍스트 안의 모든 날짜 후보. 이미 더 구체적인 패턴이 차지한 구간은 다시 쓰지 않는다."""
    t = normalize_text(text)
    taken: list[tuple[int, int]] = []
    found: list[DateCandidate] = []
    for name, pattern in _PATTERNS:
        for m in pattern.finditer(t):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            candidates = _from_match(name, m, t)
            if candidates:
                taken.append((m.start(), m.end()))
                found.extend(candidates)
    return found


def pick_expiry(lines: list[str]) -> DateCandidate | None:
    """OCR 줄 목록에서 소비기한 1개를 고른다.

    한 줄 안의 키워드뿐 아니라 줄 전체를 이어 붙인 문맥도 본다
    (예: '소비기한' 과 날짜가 다른 줄로 인식되는 경우).
    """
    candidates: list[DateCandidate] = []
    for line in lines:
        candidates.extend(find_dates(line))
    if not candidates:
        # 줄 단위로 끊긴 날짜(예: '2026.' / '10.05')를 위해 이어 붙여 한 번 더 본다.
        candidates = find_dates(" ".join(lines))
    if not candidates:
        return None
    # 1) 키워드 근처 2) 일 단위 정밀도 3) 가장 늦은 날짜
    return max(candidates, key=lambda c: (c.near_keyword, c.precision == "day", c.value))
