#!/usr/bin/env bash
# 검증셋(val) ROI+OCR 비교 A~E 를 순서대로 실행한다. 각 실행은 자원이 비었을 때만 시작하고
# (wait_for_resources), 실행 중에는 yield_guard 로 다른 작업에 양보한다. 실패하면 멈춘다.
# F(회전 재시도)는 A~E 결과를 본 뒤 최고 전처리로 따로 실행한다.
set -u
cd "$(dirname "$0")/.."
BOXES=outputs/roi_det/yolox_s_full_e80/boxes_val.json
EMPTY=outputs/roi_det/yolox_s_full_e80/boxes_val_empty.json
.venv/bin/python -c "import json; b=json.load(open('$BOXES')); json.dump({k: [] for k in b}, open('$EMPTY','w'))"

run() {  # run <이름> <boxes> <추가 인자...>
  local name=$1 boxes=$2; shift 2
  local pidf=logs/roi_val_$name.pid
  rm -f "$pidf"
  ~/scripts/wait_for_resources.sh --log "logs/wait_roi_val_$name.log" --job-log "logs/roi_val_$name.log" \
    --pid-file "$pidf" -- env OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 19 \
    .venv-ocr/bin/python scripts/roi_ocr_eval.py --boxes "$boxes" --split val --run-name "val_$name" "$@" &
  local wrapper=$!
  until [ -s "$pidf" ] || ! kill -0 "$wrapper" 2>/dev/null; do sleep 5; done
  [ -s "$pidf" ] && bash scripts/yield_guard.sh "$(cat "$pidf")" 20 "logs/yield_roi_val_$name.log" 150 70 &
  wait "$wrapper"; local rc=$?
  echo "[$(date '+%F %T')] $name rc=$rc" >> logs/roi_val_queue.log
  return $rc
}

run A_full_image "$EMPTY" --variant raw || exit 1
run B_roi_raw "$BOXES" --variant raw || exit 1
run C_roi_up2 "$BOXES" --variant up2 || exit 1
run D_roi_up2_clahe "$BOXES" --variant up2_clahe || exit 1
run E_roi_up2_clahe_close "$BOXES" --variant up2_clahe_close || exit 1
echo "[$(date '+%F %T')] QUEUE_DONE" >> logs/roi_val_queue.log
