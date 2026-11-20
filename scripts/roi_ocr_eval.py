"""ROI 박스 → 크롭 → 전처리 → OCR → 날짜 규칙 → 채점 (.venv-ocr).

    .venv-ocr/bin/python scripts/roi_ocr_eval.py --boxes outputs/roi_det/<exp>/boxes_val.json \
        --split val --variant raw --run-name <이름>

비교 원칙 (한 번에 하나만 바꾼다):
    variant  = 크롭 전처리 방식 (raw / up2 / up2_clahe / up2_clahe_close)
    fallback = 박스가 없거나 날짜를 못 찾으면 원본 전체 OCR 로 한 번 더 (기본 켬)
    rotate   = 그래도 못 찾으면 크롭을 90/180/270 도 돌려서 다시 (기본 끔, 별도 비교)
모델·전처리 선택은 val 로만 한다. eval 은 선택이 모두 끝난 뒤 한 번만.

정답:
    val  : train 의 'date' 박스 문자열 (ocr_baseline.ground_truth_train)
    eval : exp 박스의 day/month/year 라벨 (ocr_baseline.ground_truth)
출력: outputs/roi_ocr/<run-name>/predictions.csv (한 장마다 append, 재실행 시 이어서), summary.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.services.expiry_parse import find_dates, pick_expiry  # noqa: E402
from ocr_baseline import ground_truth, ground_truth_train  # noqa: E402

SRC = {"val": ("train", ROOT / "data/expdate/Products-Real/train"),
       "eval": ("evaluation", ROOT / "data/expdate/Products-Real/evaluation")}
FIELDS = ["image", "gt_date", "gt_precision", "n_boxes", "top_score", "pred_date", "pred_raw",
          "stage", "exact", "any_cand", "ocr_text", "seconds", "error"]


def crop(image: np.ndarray, box: list[float], pad: float) -> np.ndarray:
    """박스를 가로 pad·세로 2*pad 비율만큼 넓혀 자른다 (날짜 끝 글자가 잘리지 않게)."""
    x1, y1, x2, y2 = box[:4]
    w, h = x2 - x1, y2 - y1
    x1, x2 = x1 - w * pad, x2 + w * pad
    y1, y2 = y1 - h * pad * 2, y2 + h * pad * 2
    H, W = image.shape[:2]
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(W, int(x2)), min(H, int(y2))
    return image[y1:y2, x1:x2]


def preprocess(crop_img: np.ndarray, variant: str) -> np.ndarray:
    if variant == "raw":
        return crop_img
    out = crop_img
    if "up2" in variant:
        out = cv2.resize(out, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    if "clahe" in variant:
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
        out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    if "close" in variant:
        # 잉크젯 점선 글씨: 어두운 점들을 이어 붙인다 (어두운 글씨 기준 → erode = 어두운 영역 확장)
        out = cv2.erode(out, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boxes", required=True)
    parser.add_argument("--split", choices=["val", "eval"], required=True)
    parser.add_argument("--variant", default="raw", choices=["raw", "up2", "up2_clahe", "up2_clahe_close"])
    parser.add_argument("--min-score", type=float, default=0.1)
    parser.add_argument("--max-crops", type=int, default=3)
    parser.add_argument("--pad", type=float, default=0.15)
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--rotate", action="store_true")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()

    split_src, src_dir = SRC[args.split]
    annotations = json.loads((src_dir / "annotations.json").read_text(encoding="utf-8"))
    boxes = json.loads(Path(args.boxes).read_text(encoding="utf-8"))
    names = sorted(boxes)

    out_dir = ROOT / "outputs/roi_ocr" / args.run_name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(vars(args), indent=2), encoding="utf-8")
    pred_path = out_dir / "predictions.csv"
    done = set()
    if pred_path.exists():
        with pred_path.open(newline="", encoding="utf-8") as f:
            done = {r["image"] for r in csv.DictReader(f) if not r["error"]}
    todo = [n for n in names if n not in done]
    print(f"total={len(names)} done={len(done)} todo={len(todo)}", flush=True)

    from paddleocr import PaddleOCR

    ocr = PaddleOCR(lang="korean", device="cpu", cpu_threads=args.threads, enable_mkldnn=False,
                    text_detection_model_name="PP-OCRv5_mobile_det",
                    use_doc_orientation_classify=False, use_doc_unwarping=False,
                    use_textline_orientation=False)

    def read(img: np.ndarray) -> list[str]:
        return [t for page in ocr.predict(img) for t in page["rec_texts"]]

    new_file = not pred_path.exists()
    with pred_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        for i, name in enumerate(todo, start=1):
            if args.split == "val":
                gt_list, gt_precision, _ = ground_truth_train(annotations[name])
            else:
                one, gt_precision, _ = ground_truth(annotations[name])
                gt_list = [one] if one else []
            row = {k: "" for k in FIELDS}
            row.update(image=name, gt_date=";".join(d.isoformat() for d in gt_list), gt_precision=gt_precision)
            started = time.perf_counter()
            try:
                image = cv2.imread(str(src_dir / "images" / name))
                kept = [b for b in boxes[name] if b[4] >= args.min_score][: args.max_crops]
                row.update(n_boxes=len(kept), top_score=kept[0][4] if kept else "")
                lines: list[str] = []
                for b in kept:
                    lines.extend(read(preprocess(crop(image, b, args.pad), args.variant)))
                stage = "roi"
                pred = pick_expiry(lines) if lines else None
                if pred is None and args.rotate and kept:
                    for code in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE):
                        rot_lines = []
                        for b in kept:
                            rot_lines.extend(read(cv2.rotate(preprocess(crop(image, b, args.pad), args.variant), code)))
                        pred = pick_expiry(rot_lines)
                        if pred is not None:
                            lines, stage = rot_lines, "roi_rotate"
                            break
                if pred is None and not args.no_fallback:
                    lines = read(image)
                    pred, stage = pick_expiry(lines), "fallback_full"
                candidates = [c for line in lines for c in find_dates(line)]
                row.update(
                    pred_date=pred.value if pred else "",
                    pred_raw=pred.raw if pred else "",
                    stage=stage if pred else "none",
                    exact=int(pred is not None and pred.value in gt_list),
                    any_cand=int(any(c.value in gt_list for c in candidates)),
                    ocr_text=" | ".join(lines),
                )
            except Exception as exc:  # 한 장 실패로 전체를 멈추지 않는다
                row["error"] = f"{type(exc).__name__}: {exc}"[:300]
            row["seconds"] = f"{time.perf_counter() - started:.2f}"
            writer.writerow(row)
            f.flush()
            print(f"[{i}/{len(todo)}] {name} gt={row['gt_date']} pred={row['pred_date']} "
                  f"stage={row['stage']} exact={row['exact']} {row['seconds']}s {row['error']}", flush=True)

    with pred_path.open(newline="", encoding="utf-8") as f:
        latest = {r["image"]: r for r in csv.DictReader(f)}
    rows = [latest[n] for n in names if n in latest]
    scored = [r for r in rows if r["gt_date"] and not r["error"]]
    n = len(scored)
    stages: dict[str, int] = {}
    for r in scored:
        stages[r["stage"]] = stages.get(r["stage"], 0) + 1
    summary = {
        "run_name": args.run_name, "split": args.split, "variant": args.variant,
        "fallback": not args.no_fallback, "rotate": args.rotate,
        "images": len(rows), "scored": n, "errors": sum(1 for r in rows if r["error"]),
        "exact": round(sum(int(r["exact"] or 0) for r in scored) / n, 4) if n else 0.0,
        "none_found": round(stages.get("none", 0) / n, 4) if n else 0.0,
        "stages": stages,
        "mean_seconds": round(sum(float(r["seconds"]) for r in rows) / len(rows), 2) if rows else 0.0,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps(summary, ensure_ascii=False), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
