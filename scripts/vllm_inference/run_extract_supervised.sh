#!/usr/bin/env bash
# Supervisor for 03_extract_client.py: auto-restart on exit, and kill+restart on stall (hang).
# 监工：客户端退出则自动重启续跑；日志若 STALL 秒不增长则判定卡死，杀掉并重启。
# 直到 done >= TOTAL，或某一轮零进展（卡在持久失败）才停止。放进 tmux 跑，防 SSH 断开。
#
# 用法（在远程 vllm_env，服务已起）：
#   tmux new -s vllm_extract -d 'source /root/miniconda3/etc/profile.d/conda.sh && conda activate vllm_env && bash scripts/vllm_inference/run_extract_supervised.sh'
#
# 可用环境变量覆盖：STALL（卡死判定秒数，默认300）、CONCURRENCY（默认32）、TOTAL（默认684153）。
set -u
cd ~/ICKG || exit 1

OUT="data/vllm_inference/output"
DONE="$OUT/_state/done_pmids.txt"
LOG="log/vllm_extract.log"
TOTAL="${TOTAL:-684153}"
STALL="${STALL:-300}"
CONCURRENCY="${CONCURRENCY:-32}"
CMD="python scripts/vllm_inference/03_extract_client.py --concurrency ${CONCURRENCY} --temperature 0 --max-tokens 2560 --gpu-hourly-cost 7.01 --output-dir ${OUT}"

log() { echo "[sup $(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

log "supervisor 启动：STALL=${STALL}s CONCURRENCY=${CONCURRENCY} TOTAL=${TOTAL}"

while true; do
  done_n=$(wc -l < "$DONE" 2>/dev/null || echo 0)
  if [ "$done_n" -ge "$TOTAL" ]; then
    log "全部完成 done=$done_n，监工退出"
    break
  fi
  before=$done_n
  log "启动客户端（done=$done_n）"
  $CMD >> "$LOG" 2>&1 &
  cpid=$!

  last_size=$(wc -c < "$LOG" 2>/dev/null || echo 0)
  last_change=$(date +%s)
  while kill -0 "$cpid" 2>/dev/null; do
    sleep 30
    cur_size=$(wc -c < "$LOG" 2>/dev/null || echo 0)
    now=$(date +%s)
    if [ "$cur_size" -gt "$last_size" ]; then
      last_size=$cur_size
      last_change=$now
    elif [ $((now - last_change)) -ge "$STALL" ]; then
      log "卡死判定：日志 ${STALL}s 未增长 -> 杀掉客户端 $cpid"
      kill -9 "$cpid" 2>/dev/null
      break
    fi
  done
  wait "$cpid" 2>/dev/null

  after=$(wc -l < "$DONE" 2>/dev/null || echo 0)
  if [ "$after" -ge "$TOTAL" ]; then
    log "全部完成 done=$after，监工退出"
    break
  fi
  if [ "$after" -le "$before" ]; then
    log "本轮零进展（$before -> $after），疑似持久失败，监工停止"
    break
  fi
  log "客户端结束，10s 后重启续跑（$before -> $after）"
  sleep 10
done
log "supervisor 退出"
