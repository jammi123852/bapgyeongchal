#!/usr/bin/env bash
# level-0 #3: 검출 추론 입력 크기 640(기준) → 800 / 960. 박스만 다시 뽑고(GPU 수 분),
# OCR 설정은 기준 F 그대로 val 에서 비교한다. 각 단계는 자원이 빌 때만, 실행 중 양보.
set -u
cd "$(dirname "$0")/.."
CKPT=outputs/roi_det/yolox_s_full_e80/best_ckpt.pth

guarded() {  # guarded <이름> <명령...>
  local name=$1; shift
  local pidf=logs/ds_$name.pid
  rm -f "$pidf"
  ~/scripts/wait_for_resources.sh --log "logs/wait_ds_$name.log" --job-log "logs/ds_$name.log" \
    --pid-file "$pidf" -- "$@" &
  local wrapper=$!
  until [ -s "$pidf" ] || ! kill -0 "$wrapper" 2>/dev/null; do sleep 5; done
  [ -s "$pidf" ] && bash scripts/yield_guard.sh "$(cat "$pidf")" 20 "logs/yield_ds_$name.log" 150 70 &
  wait "$wrapper"; local rc=$?
  echo "[$(date '+%F %T')] $name rc=$rc" >> logs/ds_queue.log
  return $rc
}

for size in 800 960; do
  out=outputs/roi_det/yolox_s_full_e80/boxes_val_s$size.json
  guarded "detect_$size" env ROI_TEST_SIZE=$size OMP_NUM_THREADS=2 nice -n 19 \
    .venv-det/bin/python scripts/roi_detect.py --ckpt "$CKPT" --split val --out "$out" || exit 1
  test -s "$out" || { echo "[$(date '+%F %T')] missing $out" >> logs/ds_queue.log; exit 1; }
  guarded "ocr_$size" env OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 19 \
    .venv-ocr/bin/python scripts/roi_ocr_eval.py --boxes "$out" --split val --variant raw --rotate \
    --run-name "l0_detsize_$size" || exit 1
done
echo "[$(date '+%F %T')] QUEUE_DONE" >> logs/ds_queue.log
