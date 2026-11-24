"""OCR 서버 (별도 venv: .venv-ocr). 사진 → 소비기한 후보.

백엔드(app/)와 분리한 이유: PaddlePaddle 이 1.4GB 로 무겁고 numpy/opencv 버전이 백엔드와 충돌할 수 있다.
사진은 메모리에서만 처리하고 디스크에 저장하지 않는다.

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

MAX_BYTES = 8 * 1024 * 1024
# 긴 변을 이 크기로 줄인다. 폰 사진(4000px)을 그대로 넣으면 CPU 에서 수십 초 걸린다.
MAX_SIDE = 1600
DET_MODEL = os.environ.get("OCR_DET_MODEL", "PP-OCRv5_mobile_det")
# 명시하지 않으면 PaddleOCR 이 lang 을 무시하고 이 모델을 쓴다. 실험 기준선과 같은 모델로 고정.
REC_MODEL = os.environ.get("OCR_REC_MODEL", "PP-OCRv6_medium_rec")

app = FastAPI(title="SoloSafe OCR", version="0.1.0")

_engine = None
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


def decode_image(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="이미지를 읽을 수 없어요.")
    h, w = image.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return image


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "engine_loaded": str(_engine is not None).lower()}


@app.post("/expiry")
async def expiry(image: UploadFile = File(...)) -> dict:
    data = await image.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="사진이 너무 커요 (최대 8MB).")
    picture = decode_image(data)

    started = time.perf_counter()
    with _engine_lock:
        result = get_engine().predict(picture)
    lines = [t for page in result for t in page["rec_texts"]]

    # 기준일 = 오늘. 애매한 표기는 오늘 기준으로 말이 되는 해석을 고르고 나머지는 대안으로 준다.
    today = date.today()
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
        "engine": f"PaddleOCR {DET_MODEL} + {REC_MODEL}",
    }
