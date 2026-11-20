"""학습된 YOLOX 로 날짜 영역(ROI) 박스를 찾아 JSON 으로 저장한다 (.venv-det).

    .venv-det/bin/python scripts/roi_detect.py --ckpt outputs/roi_det/<exp>/best_ckpt.pth \
        --split val --out outputs/roi_det/<exp>/boxes_val.json [--overlay 20]

출력 JSON: {이미지 파일명: [[x1, y1, x2, y2, score], ...]}  (원본 좌표, 점수 내림차순, 최대 --topk 개)
--overlay N: 박스를 그린 PNG N장을 <out 폴더>/overlay_<split>/ 에 저장 (눈검증)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "configs"))

import cv2  # noqa: E402
import torch  # noqa: E402
from yolox.data.data_augment import ValTransform  # noqa: E402
from yolox.utils import postprocess  # noqa: E402

from yolox_s_expdate import Exp  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", required=True)
    parser.add_argument("--split", choices=["train", "val", "eval"], required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--conf", type=float, default=0.05, help="낮게 두고 OCR 단계에서 점수로 거른다")
    parser.add_argument("--topk", type=int, default=5)
    parser.add_argument("--overlay", type=int, default=0)
    args = parser.parse_args()

    exp = Exp()
    model = exp.get_model()
    ckpt = torch.load(args.ckpt, map_location="cpu", weights_only=False)
    model.load_state_dict(ckpt["model"])
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    preproc = ValTransform(legacy=False)

    image_dir = ROOT / "data/roi_det" / args.split
    names = sorted(p.name for p in image_dir.iterdir())
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_dir = out_path.parent / f"overlay_{args.split}"
    if args.overlay:
        overlay_dir.mkdir(exist_ok=True)

    results: dict[str, list[list[float]]] = {}
    for i, name in enumerate(names):
        image = cv2.imread(str(image_dir / name))
        ratio = min(exp.test_size[0] / image.shape[0], exp.test_size[1] / image.shape[1])
        tensor, _ = preproc(image, None, exp.test_size)
        tensor = torch.from_numpy(tensor).unsqueeze(0).float().to(device)
        with torch.no_grad():
            output = postprocess(model(tensor), exp.num_classes, args.conf, exp.nmsthre, class_agnostic=True)[0]
        boxes: list[list[float]] = []
        if output is not None:
            output = output.cpu()
            scores = output[:, 4] * output[:, 5]
            order = scores.argsort(descending=True)[: args.topk]
            for j in order.tolist():
                x1, y1, x2, y2 = (output[j, :4] / ratio).tolist()
                boxes.append([round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1), round(float(scores[j]), 4)])
        results[name] = boxes
        if i < args.overlay:
            for x1, y1, x2, y2, s in boxes[:3]:
                cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), (0, 200, 0), 4)
                cv2.putText(image, f"{s:.2f}", (int(x1), max(0, int(y1) - 8)), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 200, 0), 3)
            scale = 900 / max(image.shape[:2])
            if scale < 1:
                image = cv2.resize(image, None, fx=scale, fy=scale)
            cv2.imwrite(str(overlay_dir / f"{name.rsplit('.', 1)[0]}.png"), image)

    out_path.write_text(json.dumps(results), encoding="utf-8")
    found = sum(1 for b in results.values() if b)
    print(json.dumps({"split": args.split, "images": len(results), "with_box": found, "out": str(out_path)}))


if __name__ == "__main__":
    main()
