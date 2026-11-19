"""ExpDate 평가셋에서 OCR(PaddleOCR) + 소비기한 추출 규칙의 기준 정확도를 잰다.

실행 (OCR 전용 venv):
    .venv-ocr/bin/python scripts/ocr_baseline.py --limit 5            # 스모크
    .venv-ocr/bin/python scripts/ocr_baseline.py --run-name full       # 전체 665장

입력: data/expdate/Products-Real/evaluation/{annotations.json, images/}
출력: outputs/ocr_baseline/<run-name>/
    predictions.csv  이미지 1장 = 1행, 한 장 끝날 때마다 append (중단 후 재실행하면 이어서)
    summary.json     전체 끝난 뒤 정확도 요약

정답: annotations 의 exp 박스 dmy_ann(day/month/year). day 가 없으면 그 달 말일(precision=month).
정확도 정의 (사전 고정):
    exact      : pick_expiry 결과 날짜 == 정답 날짜
    any_cand   : OCR 텍스트에서 찾은 후보 중 하나라도 정답 (선택 규칙의 상한)
    no_cand    : 날짜 후보를 하나도 못 찾음
평가셋 이미지는 규칙 튜닝에 쓰지 않는다. 튜닝은 train 분할로만 한다.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

# CPU 스레드 제한: 다른 세션 작업과 CPU 를 나눠 쓴다. paddle import 전에 설정해야 한다.
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.expiry_parse import MONTHS, find_dates, pick_expiry  # noqa: E402

DATA_ROOT = ROOT / "data/expdate/Products-Real"
FIELDS = [
    "image",
    "gt_date",
    "gt_precision",
    "gt_raw",
    "pred_date",
    "pred_precision",
    "pred_raw",
    "pred_near_keyword",
    "pred_ambiguous",
    "exact",
    "any_cand",
    "n_cand",
    "ocr_text",
    "seconds",
    "error",
]


def ground_truth_train(entry: dict) -> tuple[list[date], str, str]:
    """train 분할: 'date' 박스(소비기한)에 dmy 라벨이 없어 문자열을 규칙으로 해석한다.

    한 사진에 소비기한 박스가 2개 이상일 수 있으므로 정답은 날짜 목록이다.
    일/월 해석이 애매한 표기는 precision 에 'ambiguous' 를 붙인다 (분석 때 따로 본다).
    """
    dates: list[date] = []
    raws: list[str] = []
    ambiguous = False
    for ann in entry["ann"]:
        if ann["cls"] != "date":
            continue
        raws.append(ann.get("transcription", ""))
        for c in find_dates(ann.get("transcription", "")):
            dates.append(c.value)
            ambiguous = ambiguous or c.ambiguous
    return dates, ("ambiguous" if ambiguous else "parsed"), " ; ".join(raws)


def ground_truth(entry: dict) -> tuple[date | None, str, str]:
    """evaluation 분할: exp 박스의 day/month/year 라벨 → 날짜. 해석 불가면 None."""
    for ann in entry["ann"]:
        if ann["cls"] != "exp":
            continue
        parts = {p["cls"]: p["transcription"].strip() for p in ann.get("dmy_ann", [])}
        raw = ann.get("transcription", "")
        try:
            y = int(parts["year"])
            y = 2000 + y if y < 100 else y
            month_raw = parts["month"].upper()
            m = MONTHS[month_raw[:3]] if month_raw[:3] in MONTHS else int(month_raw)
            if "day" in parts and parts["day"]:
                return date(y, m, int(parts["day"])), "day", raw
            return date(y, m, calendar.monthrange(y, m)[1]), "month", raw
        except (KeyError, ValueError):
            return None, "", raw
    return None, "", ""


def load_done(path: Path) -> set[str]:
    """오류 없이 끝난 이미지만 완료로 본다 (오류 행은 재실행 때 다시 시도)."""
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as f:
        return {row["image"] for row in csv.DictReader(f) if not row["error"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", default="smoke")
    # 규칙 개선(오류 분석)은 train 으로만 한다. evaluation 은 최종 점수용.
    parser.add_argument("--split", choices=["evaluation", "train"], default="evaluation")
    parser.add_argument("--limit", type=int, default=0, help="0 이면 전체")
    parser.add_argument("--threads", type=int, default=4)
    # paddlepaddle 3.3.1 CPU 에서 oneDNN 이 PP-OCRv5 를 실행하지 못한다(NotImplementedError). 기본 끔.
    parser.add_argument("--mkldnn", action="store_true")
    # 글자 위치 검출 모델. server 는 정확하지만 CPU 에서 느리다(스모크 20~50초/장).
    parser.add_argument("--det-model", default="PP-OCRv5_server_det")
    args = parser.parse_args()

    out_dir = ROOT / "outputs/ocr_baseline" / args.run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_path = out_dir / "predictions.csv"

    data = DATA_ROOT / args.split
    annotations = json.loads((data / "annotations.json").read_text(encoding="utf-8"))
    names = sorted(annotations)
    if args.limit:
        names = names[: args.limit]
    done = load_done(pred_path)
    todo = [n for n in names if n not in done]
    print(f"total={len(names)} done={len(done)} todo={len(todo)}", flush=True)

    from paddleocr import PaddleOCR  # 무거운 import 는 필요할 때만

    ocr = PaddleOCR(
        lang="korean",
        device="cpu",
        cpu_threads=args.threads,
        enable_mkldnn=args.mkldnn,
        text_detection_model_name=args.det_model,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    new_file = not pred_path.exists()
    with pred_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        for i, name in enumerate(todo, start=1):
            if args.split == "train":
                gt_list, gt_precision, gt_raw = ground_truth_train(annotations[name])
            else:
                gt_one, gt_precision, gt_raw = ground_truth(annotations[name])
                gt_list = [gt_one] if gt_one else []
            row = {k: "" for k in FIELDS}
            row.update(
                image=name,
                gt_date=";".join(d.isoformat() for d in gt_list),
                gt_precision=gt_precision,
                gt_raw=gt_raw,
            )
            started = time.perf_counter()
            try:
                result = ocr.predict(str(data / "images" / name))
                lines = [t for page in result for t in page["rec_texts"]]
                candidates = [c for line in lines for c in find_dates(line)] or find_dates(" ".join(lines))
                pred = pick_expiry(lines)
                row.update(
                    pred_date=pred.value if pred else "",
                    pred_precision=pred.precision if pred else "",
                    pred_raw=pred.raw if pred else "",
                    pred_near_keyword=int(pred.near_keyword) if pred else "",
                    pred_ambiguous=int(pred.ambiguous) if pred else "",
                    exact=int(pred is not None and pred.value in gt_list),
                    any_cand=int(any(c.value in gt_list for c in candidates)),
                    n_cand=len(candidates),
                    ocr_text=" | ".join(lines),  # 자르지 않는다 (재채점에 전체가 필요)
                )
            except Exception as exc:  # 한 장 실패로 전체를 멈추지 않는다. error 열에 남긴다.
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]
            row["seconds"] = f"{time.perf_counter() - started:.2f}"
            writer.writerow(row)
            f.flush()
            print(
                f"[{i}/{len(todo)}] {name} gt={row['gt_date']} pred={row['pred_date']} "
                f"exact={row['exact']} {row['seconds']}s {row['error']}",
                flush=True,
            )

    # 요약은 CSV 전체(이어 달리기 포함)에서 다시 계산한다.
    # 같은 이미지가 여러 번 있으면(오류 후 재시도) 마지막 행만 쓴다.
    with pred_path.open(newline="", encoding="utf-8") as f:
        latest = {r["image"]: r for r in csv.DictReader(f) if r["image"] in set(names)}
    rows = list(latest.values())
    scored = [r for r in rows if r["gt_date"] and not r["error"]]
    n = len(scored)

    def rate(key: str) -> float:
        return round(sum(int(r[key] or 0) for r in scored) / n, 4) if n else 0.0

    summary = {
        "run_name": args.run_name,
        "split": args.split,
        "images_total": len(names),
        "rows": len(rows),
        "scored": n,
        "gt_unparsed": sum(1 for r in rows if not r["gt_date"]),
        "errors": sum(1 for r in rows if r["error"]),
        "exact": rate("exact"),
        "any_cand": rate("any_cand"),
        "no_cand": round(sum(1 for r in scored if int(r["n_cand"] or 0) == 0) / n, 4) if n else 0.0,
        "mean_seconds": round(sum(float(r["seconds"]) for r in rows) / len(rows), 2) if rows else 0.0,
        "engine": f"PaddleOCR lang=korean cpu mkldnn={args.mkldnn} det={args.det_model}",
        "threads": args.threads,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
