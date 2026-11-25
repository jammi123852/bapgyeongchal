"""YOLOX-s ROI 체크포인트 → ONNX (.venv-det, CPU).

    .venv-det/bin/python scripts/export_roi_onnx.py [--ckpt ...] [--out ...]

decode_in_inference=True 로 내보내서 출력이 (1, N, 6) = cx cy w h obj cls (입력 640 픽셀 좌표).
후처리(점수·NMS)는 ocr_service/roi.py 가 numpy 로 한다. 원본 ckpt 는 건드리지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "configs"))

import torch  # noqa: E402

from yolox_s_expdate import Exp  # noqa: E402

CKPT = ROOT / "outputs/roi_det/yolox_s_full_e80/best_ckpt.pth"
CKPT_SHA256 = "836b77c8a79d3f54e14a396a42e2347360142aef8795bf1e0dacc7392e081e10"  # FINAL_CONFIG_preregistered


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ckpt", default=str(CKPT))
    parser.add_argument("--out", default=str(CKPT.parent / "best.onnx"))
    parser.add_argument("--opset", type=int, default=17)
    args = parser.parse_args()

    ckpt_path = Path(args.ckpt)
    ckpt_sha = sha256(ckpt_path)
    if ckpt_path == CKPT and ckpt_sha != CKPT_SHA256:
        raise SystemExit(f"ckpt sha256 불일치: {ckpt_sha}")

    exp = Exp()
    model = exp.get_model()
    model.load_state_dict(torch.load(ckpt_path, map_location="cpu", weights_only=False)["model"])
    model.eval()
    model.head.decode_in_inference = True

    out = Path(args.out)
    dummy = torch.zeros(1, 3, exp.test_size[0], exp.test_size[1])
    torch.onnx.export(model, (dummy,), str(out), input_names=["images"], output_names=["output"],
                      opset_version=args.opset, dynamo=False)

    import onnx

    onnx.checker.check_model(onnx.load(str(out)))
    info = {"ckpt": str(ckpt_path), "ckpt_sha256": ckpt_sha, "onnx": str(out), "onnx_sha256": sha256(out),
            "opset": args.opset, "input": [1, 3, *exp.test_size], "decode_in_inference": True}
    out.with_suffix(".json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps(info))


if __name__ == "__main__":
    main()
