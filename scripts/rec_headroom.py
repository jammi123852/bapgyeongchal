"""인식 모델 개선 여지 측정: 정답 날짜 박스를 잘라 인식(rec)만 돌리고 숫자열 일치율을 잰다 (.venv-ocr, CPU).

검출 오류를 빼고 '날짜 영역을 정확히 줬을 때 인식 모델이 숫자를 맞게 읽는가'만 본다.
이 값이 이미 매우 높으면 날짜 전용 인식 학습의 이득이 작다.

    .venv-ocr/bin/python scripts/rec_headroom.py --split train --rec-model PP-OCRv6_medium_rec

일치 기준: 인식 결과와 정답 문자열에서 숫자만 뽑아 완전히 같으면 정답 (구분자·글자 차이는 무시).
출력: outputs/rec_headroom/<split>_<rec-model>/{predictions.csv, summary.json}
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
ROOT = Path(__file__).resolve().parents[1]
SPLITS = {"train": ("train", "date")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=list(SPLITS), default="train")
    parser.add_argument("--rec-model", default="PP-OCRv6_medium_rec")
    parser.add_argument("--pad", type=float, default=0.05)
    args = parser.parse_args()

    import cv2
    from paddleocr import TextRecognition

    folder, cls = SPLITS[args.split]
    src = ROOT / "data/expdate/Products-Real" / folder
    annotations = json.loads((src / "annotations.json").read_text(encoding="utf-8"))
    out_dir = ROOT / "outputs/rec_headroom" / f"{args.split}_{args.rec_model}"
    out_dir.mkdir(parents=True, exist_ok=True)
    rec = TextRecognition(model_name=args.rec_model, device="cpu", enable_mkldnn=False)

    rows = []
    for name in sorted(annotations):
        image = None
        for k, ann in enumerate(a for a in annotations[name]["ann"] if a["cls"] == cls):
            gt = ann.get("transcription", "")
            gt_digits = re.sub(r"\D", "", gt)
            if len(gt_digits) < 4:
                continue
            if image is None:
                image = cv2.imread(str(src / "images" / name))
            x1, y1, x2, y2 = ann["bbox"]
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
            w, h = x2 - x1, y2 - y1
            H, W = image.shape[:2]
            crop = image[max(0, int(y1 - h * args.pad)) : min(H, int(y2 + h * args.pad)),
                         max(0, int(x1 - w * args.pad)) : min(W, int(x2 + w * args.pad))]
            if crop.size == 0:
                continue
            text = rec.predict(crop)[0]["rec_text"]
            pred_digits = re.sub(r"\D", "", text)
            rows.append({"image": name, "box": k, "gt": gt, "pred": text,
                         "digits_ok": int(pred_digits == gt_digits)})

    with (out_dir / "predictions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    n = len(rows)
    summary = {"split": args.split, "rec_model": args.rec_model, "crops": n,
               "digits_exact": round(sum(r["digits_ok"] for r in rows) / n, 4)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
