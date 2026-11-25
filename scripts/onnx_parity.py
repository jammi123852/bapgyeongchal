"""ONNX(onnxruntime) 검출이 torch 검출과 같은지 val 로 확인한다 (.venv-det, CPU). eval 은 쓰지 않는다.

    .venv-det/bin/python scripts/onnx_parity.py

비교 3가지 (한 장마다, OCR 에 실제로 쓰는 박스 = score >= 0.1 상위 3개 기준):
    ort   vs torch_cpu : 같은 CPU 에서 변환 자체가 맞는지
    ort   vs boxes_val.json (val 선택 때 GPU 로 만든 박스) : 서비스가 실험 조건과 같은 박스를 쓰는지
출력: outputs/roi_det/yolox_s_full_e80/onnx_parity.json (+ 불일치 이미지 목록)
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "configs"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402
from yolox.data.data_augment import ValTransform  # noqa: E402
from yolox.utils import postprocess  # noqa: E402

from ocr_service.roi import CONF, TOPK, RoiDetector  # noqa: E402
from yolox_s_expdate import Exp  # noqa: E402

EXP_DIR = ROOT / "outputs/roi_det/yolox_s_full_e80"
MIN_SCORE, MAX_CROPS = 0.1, 3  # FINAL_CONFIG_preregistered


def used(boxes: list[list[float]]) -> list[list[float]]:
    return [b for b in boxes if b[4] >= MIN_SCORE][:MAX_CROPS]


def iou(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def compare(a_all: dict, b_all: dict, names: list[str]) -> dict:
    count_mismatch, ious, score_diffs = [], [], []
    for n in names:
        a, b = used(a_all[n]), used(b_all[n])
        if len(a) != len(b):
            count_mismatch.append(n)
            continue
        for x, y in zip(a, b):
            ious.append(iou(x, y))
            score_diffs.append(abs(x[4] - y[4]))
    ious_arr, sd = np.array(ious or [1.0]), np.array(score_diffs or [0.0])
    return {"images": len(names), "count_mismatch": len(count_mismatch), "count_mismatch_images": count_mismatch,
            "boxes_compared": len(ious), "iou_min": round(float(ious_arr.min()), 4),
            "iou_mean": round(float(ious_arr.mean()), 5), "boxes_iou_below_0.95": int((ious_arr < 0.95).sum()),
            "score_absdiff_max": round(float(sd.max()), 4)}


def main() -> None:
    exp = Exp()
    model = exp.get_model()
    model.load_state_dict(torch.load(EXP_DIR / "best_ckpt.pth", map_location="cpu", weights_only=False)["model"])
    model.eval()
    torch.set_num_threads(2)
    preproc = ValTransform(legacy=False)
    detector = RoiDetector(EXP_DIR / "best.onnx", threads=2)

    image_dir = ROOT / "data/roi_det/val"
    names = sorted(p.name for p in image_dir.iterdir())
    torch_boxes, ort_boxes, ort_seconds = {}, {}, []
    for i, name in enumerate(names, start=1):
        image = cv2.imread(str(image_dir / name))
        ratio = min(exp.test_size[0] / image.shape[0], exp.test_size[1] / image.shape[1])
        tensor, _ = preproc(image, None, exp.test_size)
        with torch.no_grad():
            out = postprocess(model(torch.from_numpy(tensor).unsqueeze(0).float()), exp.num_classes, CONF,
                              exp.nmsthre, class_agnostic=True)[0]
        boxes = []
        if out is not None:
            scores = out[:, 4] * out[:, 5]
            for j in scores.argsort(descending=True)[:TOPK].tolist():
                x1, y1, x2, y2 = (out[j, :4] / ratio).tolist()
                boxes.append([round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1), round(float(scores[j]), 4)])
        torch_boxes[name] = boxes
        started = time.perf_counter()
        ort_boxes[name] = detector.detect(image)
        ort_seconds.append(time.perf_counter() - started)
        if i % 20 == 0 or i == len(names):
            print(f"[{i}/{len(names)}]", flush=True)

    gpu_boxes = json.loads((EXP_DIR / "boxes_val.json").read_text(encoding="utf-8"))
    result = {
        "onnx": str(EXP_DIR / "best.onnx"),
        "rule": f"score >= {MIN_SCORE}, top {MAX_CROPS}",
        "ort_vs_torch_cpu": compare(ort_boxes, torch_boxes, names),
        "ort_vs_boxes_val_gpu": compare(ort_boxes, gpu_boxes, names),
        "ort_seconds_mean": round(float(np.mean(ort_seconds)), 4),
        "ort_seconds_p95": round(float(np.percentile(ort_seconds, 95)), 4),
    }
    (EXP_DIR / "onnx_parity.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("SUMMARY", json.dumps(result), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
