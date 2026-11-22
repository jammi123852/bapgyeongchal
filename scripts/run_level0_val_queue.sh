#!/usr/bin/env bash
# level-0(입력·인식 단계) 비교: 기준 F(ROI raw + 회전 + 전체 복귀, PP-OCRv6_medium_rec, pad 0.15) 대비
# 한 번에 하나만 바꾼 실행들을 val 에서 순서대로 돌린다. 자원이 빌 때만 시작, 실행 중 양보.
set -u
cd "$(dirname "$0")/.."
BOXES=outputs/roi_det/yolox_s_full_e80/boxes_val.json
BASE=(--boxes "$BOXES" --split val --variant raw --rotate)

run() {  # run <이름> <추가 인자...>  (추가 인자는 BASE 뒤에 붙어 해당 값을 덮어쓴다)
  local name=$1; shift
  local pidf=logs/l0_$name.pid
  rm -f "$pidf"
  ~/scripts/wait_for_resources.sh --log "logs/wait_l0_$name.log" --job-log "logs/l0_$name.log" \
    --pid-file "$pidf" -- env OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 nice -n 19 \
    .venv-ocr/bin/python scripts/roi_ocr_eval.py "${BASE[@]}" --run-name "l0_$name" "$@" &
  local wrapper=$!
  until [ -s "$pidf" ] || ! kill -0 "$wrapper" 2>/dev/null; do sleep 5; done
  [ -s "$pidf" ] && bash scripts/yield_guard.sh "$(cat "$pidf")" 20 "logs/yield_l0_$name.log" 150 70 &
  wait "$wrapper"; local rc=$?
  echo "[$(date '+%F %T')] $name rc=$rc" >> logs/l0_queue.log
  return $rc
}

run F_repro_v6 || exit 1                                   # 재현: 이전 val_F 95.27% 와 같아야 함
run rec_korean_v5 --rec-model korean_PP-OCRv5_mobile_rec || exit 1
run rec_en_v5 --rec-model en_PP-OCRv5_mobile_rec || exit 1
run rec_server_v5 --rec-model PP-OCRv5_server_rec || exit 1
run rec_v6_small --rec-model PP-OCRv6_small_rec || exit 1
run rec_only_v6 --rec-only || exit 1
run pad_005 --pad 0.05 || exit 1
run pad_025 --pad 0.25 || exit 1
run pad_040 --pad 0.40 || exit 1
run pre_gblur --variant gblur || exit 1
run pre_binarize --variant binarize || exit 1
echo "[$(date '+%F %T')] QUEUE_DONE" >> logs/l0_queue.log
