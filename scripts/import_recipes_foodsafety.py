"""식품안전나라 조리식품 레시피(COOKRCP01) → recipes 테이블 (.venv, 무료 공공 API).

    .venv/bin/python scripts/import_recipes_foodsafety.py            # .env 의 FOODSAFETY_API_KEY 로 전체
    .venv/bin/python scripts/import_recipes_foodsafety.py --sample   # data/recipes/sample5.json (키 없이 개발용)

- 1000 개씩 받는다 (API 한 번 최대 1000). 받은 원본은 data/recipes/foodsafety_<start>_<end>.json 에 저장해
  다시 실행하면 파일이 있는 구간은 API 를 부르지 않는다 (resume).
- 같은 RCP_SEQ 는 덮어쓴다 (upsert). 재료를 하나도 못 뽑은 레시피는 건너뛰고 개수를 보고한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.enums import RecipeSource  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models import Recipe  # noqa: E402
from app.services.ingredients import looks_like_title, parse_ingredients  # noqa: E402
from app.services.recipes import build_ingredients  # noqa: E402

OUT_DIR = ROOT / "data/recipes"
PAGE = 1000
URL = "http://openapi.foodsafetykorea.go.kr/api/{key}/COOKRCP01/json/{start}/{end}"


def fetch(key: str, start: int, end: int) -> dict:
    path = OUT_DIR / f"foodsafety_{start}_{end}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    with urllib.request.urlopen(URL.format(key=key, start=start, end=end), timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    result = data.get("COOKRCP01", {}).get("RESULT", {})
    if result.get("CODE") != "INFO-000":
        raise SystemExit(f"API 오류 {start}-{end}: {result}")
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(1)
    return data


def to_https(url: str | None) -> str | None:
    if not url:
        return None
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def to_row(r: dict, fetched_at: datetime) -> dict | None:
    name = r["RCP_NM"].strip()
    names = [n for n in parse_ingredients(r.get("RCP_PARTS_DTLS") or "") if not looks_like_title(n, name)]
    ingredients = build_ingredients(names)
    if not ingredients:
        return None
    # 원문 끝의 사진 표시 글자('...찐다.c') 한 개만 지운다. '5g' 같은 단위는 건드리지 않는다.
    steps = [re.sub(r"(?<=[.!?)가-힣])[a-z]$", "", r[f"MANUAL{i:02d}"].strip()).strip()
             for i in range(1, 21) if (r.get(f"MANUAL{i:02d}") or "").strip()]
    return {
        "source": RecipeSource.FOODSAFETY, "external_id": str(r["RCP_SEQ"]), "name": name,
        # 폰은 기본 설정에서 http 이미지를 막는다 → https 로 (2026-09-30 https 200 확인)
        "category": r.get("RCP_PAT2") or None, "image_url": to_https(r.get("ATT_FILE_NO_MAIN")),
        "ingredients": ingredients, "steps": steps or None, "fetched_at": fetched_at,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(UTC)

    if args.sample:
        rows = json.loads((OUT_DIR / "sample5.json").read_text(encoding="utf-8"))["COOKRCP01"]["row"]
    else:
        key = get_settings().foodsafety_api_key
        if not key:
            raise SystemExit("FOODSAFETY_API_KEY 가 .env 에 없습니다.")
        first = fetch(key, 1, PAGE)
        total = int(first["COOKRCP01"]["total_count"])
        rows = list(first["COOKRCP01"]["row"])
        for start in range(PAGE + 1, total + 1, PAGE):
            rows += fetch(key, start, min(start + PAGE - 1, total))["COOKRCP01"]["row"]
        print(f"total_count={total} received={len(rows)}", flush=True)

    values = [v for v in (to_row(r, fetched_at) for r in rows) if v is not None]
    skipped = len(rows) - len(values)
    with SessionLocal() as db:
        for v in values:
            stmt = insert(Recipe).values(**v)
            db.execute(stmt.on_conflict_do_update(
                constraint="uq_recipes_source_external_id",
                set_={k: stmt.excluded[k] for k in ("name", "category", "image_url", "ingredients", "steps", "fetched_at")},
            ))
        db.commit()
    per = [len(v["ingredients"]) for v in values]
    print(json.dumps({"upserted": len(values), "skipped_no_ingredients": skipped,
                      "ingredients_mean": round(sum(per) / len(per), 1) if per else 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
