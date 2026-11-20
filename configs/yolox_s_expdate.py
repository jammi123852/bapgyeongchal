"""YOLOX-s 설정: 소비기한 인쇄 영역(expdate) 1클래스 검출.

데이터: scripts/det_prepare.py 가 만든 data/roi_det (COCO 형식)
환경변수로 스모크/전체 실행을 바꾼다 (코드 수정 없이 같은 설정 파일을 쓰기 위해):
    ROI_TRAIN_ANN   기본 instances_train.json (스모크: instances_train_smoke100.json)
    ROI_MAX_EPOCH   기본 80
    ROI_WORKERS     기본 2 (다른 세션과 CPU 공유)

학습:
    .venv-det/bin/python third_party/YOLOX/tools/train.py -f configs/yolox_s_expdate.py \
        -d 1 -b 8 --fp16 -c weights/yolox_s.pth
"""

import os
from pathlib import Path

from yolox.exp import Exp as BaseExp

ROOT = Path(__file__).resolve().parents[1]


class Exp(BaseExp):
    def __init__(self):
        super().__init__()
        # YOLOX-s
        self.depth = 0.33
        self.width = 0.50
        self.exp_name = os.environ.get("ROI_EXP_NAME", "yolox_s_expdate")
        self.output_dir = str(ROOT / "outputs/roi_det")

        self.num_classes = 1
        self.data_dir = str(ROOT / "data/roi_det")
        self.train_ann = os.environ.get("ROI_TRAIN_ANN", "instances_train.json")
        self.val_ann = "instances_val.json"  # 모델 선택은 val 로만. eval 은 여기 넣지 않는다.

        self.max_epoch = int(os.environ.get("ROI_MAX_EPOCH", "80"))
        self.no_aug_epochs = min(10, self.max_epoch // 4)
        self.warmup_epochs = min(3, self.max_epoch // 5)
        self.eval_interval = int(os.environ.get("ROI_EVAL_INTERVAL", "5"))
        self.print_interval = 10
        self.data_num_workers = int(os.environ.get("ROI_WORKERS", "2"))

        # 일반화용 증강. 글자 좌우 반전은 실제 포장에 없어 끈다.
        self.flip_prob = 0.0
        self.degrees = 15.0  # 기울여 찍은 사진
        self.shear = 2.0
        self.translate = 0.1
        self.mosaic_prob = 1.0
        self.mosaic_scale = (0.5, 1.5)
        self.mixup_prob = 0.5
        self.hsv_prob = 1.0

    def get_dataset(self, cache: bool = False, cache_type: str = "ram"):
        from yolox.data import COCODataset, TrainTransform

        return COCODataset(
            data_dir=self.data_dir,
            json_file=self.train_ann,
            name="train",
            img_size=self.input_size,
            preproc=TrainTransform(max_labels=10, flip_prob=self.flip_prob, hsv_prob=self.hsv_prob),
            cache=cache,
            cache_type=cache_type,
        )

    def get_eval_dataset(self, **kwargs):
        from yolox.data import COCODataset, ValTransform

        return COCODataset(
            data_dir=self.data_dir,
            json_file=self.val_ann,
            name="val",
            img_size=self.test_size,
            preproc=ValTransform(legacy=kwargs.get("legacy", False)),
        )
