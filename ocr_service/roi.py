"""날짜 영역(ROI) 검출: YOLOX-s ONNX + onnxruntime(CPU). torch 없이 돈다 (.venv-ocr).

scripts/roi_detect.py (torch) 와 같은 결과를 내도록 전처리·후처리를 그대로 옮겼다:
    전처리  yolox.data.data_augment.preproc  — 왼쪽 위 정렬 letterbox, 채움값 114, BGR, 정규화 없음
    후처리  yolox.utils.postprocess(class_agnostic=True) — score = obj * cls, conf 이상만, NMS
일치 여부는 scripts/onnx_parity.py 가 val 로 확인한다.

ONNX 만들기 (.venv-det):
    .venv-det/bin/python scripts/export_roi_onnx.py
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ONNX = ROOT / "outputs/roi_det/yolox_s_full_e80/best.onnx"
INPUT_SIZE = 640  # 학습·val 선택 모두 640 (800/960 은 val 에서 더 나빴다)
CONF = 0.05  # roi_detect.py 기본값. 실제 사용 박스는 OCR 단계에서 min_score 로 다시 거른다
NMS_IOU = 0.65  # yolox Exp.nmsthre
TOPK = 5


def preproc(image: np.ndarray, size: int = INPUT_SIZE) -> tuple[np.ndarray, float]:
    padded = np.full((size, size, 3), 114, dtype=np.uint8)
    r = min(size / image.shape[0], size / image.shape[1])
    resized = cv2.resize(image, (int(image.shape[1] * r), int(image.shape[0] * r)),
                         interpolation=cv2.INTER_LINEAR).astype(np.uint8)
    padded[: resized.shape[0], : resized.shape[1]] = resized
    return np.ascontiguousarray(padded.transpose(2, 0, 1), dtype=np.float32)[None], r


def nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> list[int]:
    """torchvision.ops.nms 와 같은 규칙: 점수 순으로 남기고 IoU > iou_thr 인 것을 지운다."""
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[1:][iou <= iou_thr]
    return keep


class RoiDetector:
    def __init__(self, onnx_path: str | Path = DEFAULT_ONNX, threads: int = 2):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(onnx_path), options, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def detect(self, image: np.ndarray) -> list[list[float]]:
        """원본 좌표 [[x1, y1, x2, y2, score], ...] (점수 내림차순, 최대 TOPK 개)."""
        tensor, r = preproc(image)
        pred = self.session.run(None, {self.input_name: tensor})[0][0]  # (N, 6): cx cy w h obj cls
        scores = pred[:, 4] * pred[:, 5]
        mask = scores >= CONF
        pred, scores = pred[mask], scores[mask]
        if not len(pred):
            return []
        boxes = np.stack([pred[:, 0] - pred[:, 2] / 2, pred[:, 1] - pred[:, 3] / 2,
                          pred[:, 0] + pred[:, 2] / 2, pred[:, 1] + pred[:, 3] / 2], axis=1)
        keep = nms(boxes, scores, NMS_IOU)
        keep = sorted(keep, key=lambda k: -scores[k])[:TOPK]
        return [[round(float(v / r), 1) for v in boxes[k]] + [round(float(scores[k]), 4)] for k in keep]
