"""ExpDate → YOLOX(COCO 형식) 날짜 영역(ROI) 검출 데이터.

클래스 1개: expdate (train 의 'date' 박스, evaluation 의 'exp' 박스 = 소비기한 인쇄 영역)
분할:
    train 1102장 → train 85% / val 15% (SEED 고정 정수, 모델·전처리 선택은 val 로만)
    evaluation 665장 → eval (최종 1회 측정용. 선택에 쓰지 않는다)

출력: data/roi_det/
    annotations/instances_{train,val,eval}.json
    {train,val,eval}/<이미지>  (원본으로의 symlink, 복사하지 않음)
    check_overlay/*.png         (정답 박스 눈검증용, --overlay N)

실행: .venv/bin/python scripts/det_prepare.py --overlay 12
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/expdate/Products-Real"
OUT = ROOT / "data/roi_det"
SEED = 20260929  # 고정 정수 (hash() 금지: 프로세스마다 달라짐)
VAL_RATIO = 0.15
CATEGORY = {"id": 1, "name": "expdate"}
SOURCE_CLASS = {"train": "date", "evaluation": "exp"}


def to_coco(split_src: str, names: list[str], annotations: dict) -> dict:
    images, anns = [], []
    for image_id, name in enumerate(names, start=1):
        entry = annotations[name]
        images.append(
            {"id": image_id, "file_name": name, "width": entry["width"], "height": entry["height"]}
        )
        for ann in entry["ann"]:
            if ann["cls"] != SOURCE_CLASS[split_src]:
                continue
            x1, y1, x2, y2 = ann["bbox"]
            x1, x2 = sorted((x1, x2))
            y1, y2 = sorted((y1, y2))
            w, h = x2 - x1, y2 - y1
            if w <= 1 or h <= 1:
                continue
            anns.append(
                {
                    "id": len(anns) + 1,
                    "image_id": image_id,
                    "category_id": CATEGORY["id"],
                    "bbox": [x1, y1, w, h],
                    "area": w * h,
                    "iscrowd": 0,
                }
            )
    return {"images": images, "annotations": anns, "categories": [CATEGORY]}


def link_images(split_src: str, names: list[str], out_name: str) -> None:
    folder = OUT / out_name
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        link = folder / name
        if not link.exists():
            link.symlink_to(SRC / split_src / "images" / name)


def overlay(coco: dict, out_name: str, count: int) -> None:
    import cv2  # 눈검증 때만 필요

    folder = OUT / "check_overlay"
    folder.mkdir(parents=True, exist_ok=True)
    by_image: dict[int, list] = {}
    for ann in coco["annotations"]:
        by_image.setdefault(ann["image_id"], []).append(ann["bbox"])
    rnd = random.Random(SEED)
    for image in rnd.sample(coco["images"], min(count, len(coco["images"]))):
        picture = cv2.imread(str(OUT / out_name / image["file_name"]))
        for x, y, w, h in by_image.get(image["id"], []):
            cv2.rectangle(picture, (int(x), int(y)), (int(x + w), int(y + h)), (0, 0, 255), 4)
        scale = 900 / max(picture.shape[:2])
        if scale < 1:
            picture = cv2.resize(picture, None, fx=scale, fy=scale)
        cv2.imwrite(str(folder / f"{out_name}_{image['file_name'].rsplit('.', 1)[0]}.png"), picture)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overlay", type=int, default=0, help="분할마다 눈검증 PNG 개수")
    args = parser.parse_args()

    (OUT / "annotations").mkdir(parents=True, exist_ok=True)
    summary = {}

    train_ann = json.loads((SRC / "train/annotations.json").read_text(encoding="utf-8"))
    names = sorted(train_ann)
    random.Random(SEED).shuffle(names)
    n_val = round(len(names) * VAL_RATIO)
    splits = {
        "train": ("train", sorted(names[n_val:]), train_ann),
        "val": ("train", sorted(names[:n_val]), train_ann),
    }
    eval_ann = json.loads((SRC / "evaluation/annotations.json").read_text(encoding="utf-8"))
    splits["eval"] = ("evaluation", sorted(eval_ann), eval_ann)

    for out_name, (split_src, split_names, annotations) in splits.items():
        coco = to_coco(split_src, split_names, annotations)
        (OUT / "annotations" / f"instances_{out_name}.json").write_text(
            json.dumps(coco, ensure_ascii=False), encoding="utf-8"
        )
        link_images(split_src, split_names, out_name)
        no_box = len(coco["images"]) - len({a["image_id"] for a in coco["annotations"]})
        summary[out_name] = {
            "images": len(coco["images"]),
            "boxes": len(coco["annotations"]),
            "images_without_box": no_box,
        }
        if args.overlay:
            overlay(coco, out_name, args.overlay)

    # 누수 확인: train/val 이미지가 겹치지 않아야 한다.
    overlap = set(splits["train"][1]) & set(splits["val"][1])
    summary["train_val_overlap"] = len(overlap)
    summary["seed"] = SEED
    (OUT / "prepare_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
