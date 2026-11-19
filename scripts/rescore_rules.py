"""저장된 OCR 텍스트에 '이전 규칙'과 '현재 규칙'을 같은 입력으로 적용해 비교한다 (OCR 재실행 없음).

    .venv/bin/python scripts/rescore_rules.py <predictions.csv> <이전 expiry_parse.py 경로>

- 정답(gt_date)은 CSV 기록값을 그대로 쓴다 (규칙을 바꿔도 정답이 따라 바뀌지 않게).
- CSV 의 exact 열과 비교하지 않는다. 예전 CSV 는 ocr_text 를 500자에서 잘라 저장해서
  같은 규칙이라도 재채점 점수가 실제 실행 점수보다 낮다 (train 87.6% → 81.1%).
  그래서 두 규칙 모두 '저장된 같은 텍스트'로 채점하고, 차이는 같은 이미지끼리 짝지은
  paired bootstrap 으로 신뢰구간을 낸다.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services import expiry_parse as current  # noqa: E402


def load_rules(path: str):
    spec = importlib.util.spec_from_file_location("previous_rules", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["previous_rules"] = module  # dataclass 가 모듈을 찾을 수 있게
    spec.loader.exec_module(module)
    return module


def score(rules, rows: list[dict]) -> list[int]:
    out = []
    for r in rows:
        gts = set(r["gt_date"].split(";"))
        pred = rules.pick_expiry(r["ocr_text"].split(" | ")) if r["ocr_text"] else None
        out.append(int(pred is not None and pred.value.isoformat() in gts))
    return out


def ci(values: list[float], n: int = 2000, seed: int = 42) -> tuple[float, float]:
    rnd = random.Random(seed)
    means = sorted(sum(rnd.choice(values) for _ in values) / len(values) for _ in range(n))
    return round(means[int(0.025 * n)], 4), round(means[int(0.975 * n)], 4)


def main(csv_path: str, previous_path: str) -> None:
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["gt_date"] and not r["error"]]
    previous = score(load_rules(previous_path), rows)
    now = score(current, rows)
    diff = [b - a for a, b in zip(previous, now)]
    n = len(rows)
    print(
        json.dumps(
            {
                "file": csv_path,
                "n": n,
                "truncated_texts": sum(len(r["ocr_text"]) >= 500 for r in rows),
                "previous_exact": round(sum(previous) / n, 4),
                "current_exact": round(sum(now) / n, 4),
                "current_ci95": ci(now),
                "delta": round(sum(diff) / n, 4),
                "delta_ci95_paired": ci(diff),
                "fixed": sum(d > 0 for d in diff),
                "broken": sum(d < 0 for d in diff),
                "broken_images": [r["image"] for r, d in zip(rows, diff) if d < 0][:20],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
