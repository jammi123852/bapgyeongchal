#!/usr/bin/env bash
# 최하위 우선순위 작업용 양보 감시.
# 우리 작업 프로세스 트리 '밖'에서 자원을 쓰면 우리 트리 전체를 SIGSTOP, 조용해지면 SIGCONT.
# 다른 프로세스는 절대 건드리지 않는다. 작업이 끝나면 함께 종료한다.
#
# 양보 조건 (하나라도 해당하면 멈춤):
#   - 우리 트리 밖의 GPU compute 프로세스가 있음
#   - 우리 트리 밖 프로세스들의 CPU 합계가 CPU_BUSY% 이상 (top 순간값, 100% = 1코어)
#   - 시스템 RAM 사용률이 RAM_BUSY% 이상
# 재개 조건: 위 조건이 모두 풀린 상태가 연속 RESUME_STABLE 회
#
# usage: yield_guard.sh <job_pid> [interval_sec=20] [log] [cpu_busy_pct=150] [ram_busy_pct=70]
JOB=$1; INT=${2:-20}; LOG=${3:-/dev/stdout}; CPU_BUSY=${4:-150}; RAM_BUSY=${5:-70}
RESUME_STABLE=2
PAUSED=0; CALM=0

tree() { local p=$1; echo "$p"; for c in $(ps -o pid= --ppid "$p"); do tree "$c"; done; }
log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

# 감시가 어떤 이유로든 끝나면 우리 작업을 멈춘 채로 두지 않는다.
trap 'kill -CONT $(tree "$JOB") 2>/dev/null' EXIT

log "yield guard start job=$JOB interval=${INT}s cpu_busy=${CPU_BUSY}% ram_busy=${RAM_BUSY}%"
while kill -0 "$JOB" 2>/dev/null; do
  MINE=" $(tree "$JOB" | tr '\n' ' ') $$ "

  GPU_OTHERS=""
  for g in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null); do
    [[ "$MINE" == *" $g "* ]] || GPU_OTHERS="$GPU_OTHERS $g"
  done

  # top 두 번째 샘플(2초 간격)의 순간 %CPU. 우리 트리와 top 자신은 제외.
  OTHER_CPU=$(top -b -n 2 -d 2 -w 512 | awk -v mine="$MINE" '
    /^top -/ {iter++; next}
    iter==2 && $1 ~ /^[0-9]+$/ {
      if (index(mine, " " $1 " ") == 0 && $12 != "top") s += $9
    }
    END {printf "%d", s}')
  RAM_PCT=$(free | awk '/^Mem:/ {printf "%d", ($2 - $7) * 100 / $2}')

  REASON=""
  [[ -n "$GPU_OTHERS" ]] && REASON="$REASON gpu:$GPU_OTHERS"
  (( OTHER_CPU >= CPU_BUSY )) && REASON="$REASON cpu_others=${OTHER_CPU}%"
  (( RAM_PCT >= RAM_BUSY )) && REASON="$REASON ram=${RAM_PCT}%"

  if [[ -n "$REASON" ]]; then
    CALM=0
    if (( PAUSED == 0 )); then
      kill -STOP $(tree "$JOB") 2>/dev/null; PAUSED=1
      log "PAUSE:$REASON"
    fi
  elif (( PAUSED == 1 )); then
    CALM=$((CALM + 1))
    if (( CALM >= RESUME_STABLE )); then
      kill -CONT $(tree "$JOB") 2>/dev/null; PAUSED=0; CALM=0
      log "RESUME (cpu_others=${OTHER_CPU}% ram=${RAM_PCT}%)"
    fi
  fi
  sleep "$INT"
done
# 작업이 멈춘 채로 끝나는 일은 없지만, 혹시 남은 자식이 있으면 풀어준다.
log "job ended; yield guard exit"
