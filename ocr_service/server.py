"""OCR 서버 (별도 venv: .venv-ocr). 사진 → 소비기한 후보.

백엔드(app/)와 분리한 이유: PaddlePaddle 이 1.4GB 로 무겁고 numpy/opencv 버전이 백엔드와 충돌할 수 있다.
사진은 메모리에서만 처리하고 디스크에 저장하지 않는다.

흐름 (outputs/roi_ocr/FINAL_CONFIG_preregistered.json 과 같은 설정, eval 85.5% vs 전체이미지 82.1%):
    1. 원본 해상도에서 날짜 영역(ROI) 검출 (YOLOX-s ONNX, ocr_service/roi.py)
    2. score >= 0.1 상위 3개 박스를 pad 0.15 로 원본에서 잘라 OCR
    3. 날짜를 못 찾으면 크롭을 90/180/270 도 돌려서 다시
    4. 그래도 없으면 전체 사진 OCR (긴 변 1600px — 실험의 fallback 은 원본 해상도였다)
ONNX 파일이 없으면 1 ~ 3 을 건너뛰고 4 만 한다 (stage="full").

실행:
    .venv-ocr/bin/uvicorn ocr_service.server:app --host 127.0.0.1 --port 8001
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import date
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402

from app.services.expiry_parse import find_dates, pick_expiry  # noqa: E402
from ocr_service.roi import DEFAULT_ONNX, RoiDetector  # noqa: E402

MAX_BYTES = 8 * 1024 * 1024
# 긴 변을 이 크기로 줄인다. 폰 사진(4000px)을 그대로 넣으면 CPU 에서 수십 초 걸린다.
MAX_SIDE = 1600
DET_MODEL = os.environ.get("OCR_DET_MODEL", "PP-OCRv5_mobile_det")
# 명시하지 않으면 PaddleOCR 이 lang 을 무시하고 이 모델을 쓴다. 실험 기준선과 같은 모델로 고정.
REC_MODEL = os.environ.get("OCR_REC_MODEL", "PP-OCRv6_medium_rec")
ROI_ONNX = Path(os.environ.get("OCR_ROI_ONNX", str(DEFAULT_ONNX)))
# 사전등록 최종 설정 (val 로만 선택)
ROI_MIN_SCORE = 0.1
ROI_MAX_CROPS = 3
ROI_PAD = 0.15

app = FastAPI(title="SoloSafe OCR", version="0.2.0")

_engine = None
_detector = None
_engine_lock = threading.Lock()  # PaddleOCR 인스턴스는 한 번에 한 요청만 처리한다.


def get_engine():
    global _engine
    if _engine is None:
        from paddleocr import PaddleOCR

        _engine = PaddleOCR(
            device="cpu",
            cpu_threads=int(os.environ.get("OMP_NUM_THREADS", "4")),
            enable_mkldnn=False,  # paddlepaddle 3.3.1 CPU oneDNN 이 PP-OCRv5 에서 실패한다
            text_detection_model_name=DET_MODEL,
            text_recognition_model_name=REC_MODEL,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    return _engine


def get_detector() -> RoiDetector | None:
    global _detector
    if _detector is None and ROI_ONNX.exists():
        _detector = RoiDetector(ROI_ONNX, threads=int(os.environ.get("OMP_NUM_THREADS", "4")))
    return _detector


def decode_image(data: bytes) -> np.ndarray:
    """원본 해상도 그대로 돌려준다 (ROI 크롭은 원본에서 자른다)."""
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="이미지를 읽을 수 없어요.")
    return image


def shrink(image: np.ndarray) -> np.ndarray:
    h, w = image.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return image


def crop(image: np.ndarray, box: list[float], pad: float = ROI_PAD) -> np.ndarray:
    """박스를 가로 pad·세로 2*pad 비율만큼 넓혀 자른다 (scripts/roi_ocr_eval.py 와 같음)."""
    x1, y1, x2, y2 = box[:4]
    w, h = x2 - x1, y2 - y1
    x1, x2 = x1 - w * pad, x2 + w * pad
    y1, y2 = y1 - h * pad * 2, y2 + h * pad * 2
    H, W = image.shape[:2]
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = min(W, int(x2)), min(H, int(y2))
    return image[y1:y2, x1:x2]


def read_lines(engine, image: np.ndarray) -> list[str]:
    return [t for page in engine.predict(image) for t in page["rec_texts"]]


def read_expiry(image: np.ndarray, today: date) -> tuple[list[str], str, int]:
    """(OCR 줄, stage, 쓴 박스 수). stage = roi / roi_rotate / full."""
    engine = get_engine()
    detector = get_detector()
    kept: list[list[float]] = []
    if detector is not None:
        kept = [b for b in detector.detect(image) if b[4] >= ROI_MIN_SCORE][:ROI_MAX_CROPS]
    crops = [c for c in (crop(image, b) for b in kept) if c.size]
    if crops:
        lines = [t for c in crops for t in read_lines(engine, c)]
        if pick_expiry(lines, today) is not None:
            return lines, "roi", len(crops)
        for code in (cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_180, cv2.ROTATE_90_COUNTERCLOCKWISE):
            rot_lines = [t for c in crops for t in read_lines(engine, cv2.rotate(c, code))]
            if pick_expiry(rot_lines, today) is not None:
                return rot_lines, "roi_rotate", len(crops)
    return read_lines(engine, shrink(image)), "full", len(crops)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "engine_loaded": str(_engine is not None).lower(),
        "roi_model": str(ROI_ONNX.exists()).lower(),
    }


@app.post("/expiry")
async def expiry(image: UploadFile = File(...)) -> dict:
    data = await image.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="사진이 너무 커요 (최대 8MB).")
    picture = decode_image(data)

    # 기준일 = 오늘. 애매한 표기는 오늘 기준으로 말이 되는 해석을 고르고 나머지는 대안으로 준다.
    today = date.today()
    started = time.perf_counter()
    with _engine_lock:
        lines, stage, roi_boxes = read_expiry(picture, today)

    candidates = [c for line in lines for c in find_dates(line, today)] or find_dates(" ".join(lines), today)
    best = pick_expiry(lines, today)

    def as_json(c) -> dict:
        return {
            "date": c.value.isoformat(),
            "precision": c.precision,
            "raw": c.raw,
            "near_keyword": c.near_keyword,
            "ambiguous": c.ambiguous,
            "alternatives": [d.isoformat() for d in c.alternatives],
        }

    return {
        "best": as_json(best) if best else None,
        "candidates": [as_json(c) for c in candidates],
        "lines": lines,
        "seconds": round(time.perf_counter() - started, 2),
        "stage": stage,
        "roi_boxes": roi_boxes,
        "engine": f"YOLOX-s ROI + PaddleOCR {DET_MODEL} + {REC_MODEL}" if get_detector() else f"PaddleOCR {DET_MODEL} + {REC_MODEL}",
    }
