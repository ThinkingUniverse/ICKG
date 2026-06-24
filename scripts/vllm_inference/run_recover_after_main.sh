#!/usr/bin/env bash
# 等主推理结束 → 监工式跑 06 截断补尾(全部截断篇, max_tokens6144 / temp0.5)→ 最终合并。
# 可中断可续跑：杀掉本会话即中断；重新启动本脚本即从 recovered_pmids.txt 续跑(主推理已完成会直接进补尾)。
# 放进 tmux 跑，防 SSH 断开。依赖 vllm_serve 服务在线。
#
# 启动：
#   tmux new -s vllm_recover -d 'source /root/miniconda3/etc/profile.d/conda.sh && conda activate vllm_env && bash scripts/vllm_inference/run_recover_after_main.sh'
# 中断：tmux kill-session -t vllm_recover ; pkill -f 06_recover_truncated
# 续跑：再次用上面的 tmux 命令启动即可。
set -u
cd ~/ICKG || exit 1

OUT="data/vllm_inference/output"
DONE="$OUT/_state/done_pmids.txt"
TRUNC="$OUT/truncated.jsonl"
RECDONE="$OUT/recover/_state/recovered_pmids.txt"
LOG="log/vllm_recover.log"
TOTAL="${TOTAL:-684153}"
STALL="${STALL:-600}"
CONC="${RECCONC:-16}"
PY="python scripts/vllm_inference/06_recover_truncated.py"

log() { echo "[rec $(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }
cnt() { local n; n=$(wc -l < "$1" 2>/dev/null); echo "${n:-0}" | tr -d ' '; }

log "编排启动：等待主推理结束（done>=$TOTAL 或 vllm_extract 会话退出）"
while :; do
  d=$(cnt "$DONE")
  if [ "${d:-0}" -ge "$TOTAL" ]; then log "主推理完成 done=$d"; break; fi
  if ! tmux has-session -t vllm_extract 2>/dev/null; then log "主推理监工已退出(done=$d)，视为主推理结束"; break; fi
  sleep 120
done

log "进入截断补尾（concurrency=$CONC, max_tokens=6144, temp=0.5, --apply）"
while :; do
  tt=$(cnt "$TRUNC"); rd=$(cnt "$RECDONE")
  if [ "${tt:-0}" -gt 0 ] && [ "${rd:-0}" -ge "${tt:-0}" ]; then
    log "补尾已全部完成 recovered=$rd >= truncated=$tt"; break
  fi
  before="${rd:-0}"
  log "启动 06 补尾（recovered=$rd / truncated=$tt）"
  $PY --concurrency "$CONC" --apply >> "$LOG" 2>&1 &
  cpid=$!
  lsz=$(wc -c < "$LOG" 2>/dev/null || echo 0); lc=$(date +%s)
  while kill -0 "$cpid" 2>/dev/null; do
    sleep 30
    cs=$(wc -c < "$LOG" 2>/dev/null || echo 0); now=$(date +%s)
    if [ "${cs:-0}" -gt "${lsz:-0}" ]; then lsz=$cs; lc=$now
    elif [ $((now - lc)) -ge "$STALL" ]; then log "卡死判定(${STALL}s 日志未增长)，杀掉 06 $cpid"; kill -9 "$cpid" 2>/dev/null; break; fi
  done
  wait "$cpid" 2>/dev/null
  after=$(cnt "$RECDONE")
  if [ "${after:-0}" -le "$before" ]; then log "本轮零进展（$before -> $after），停止重试（可能持久失败/服务异常）"; break; fi
  log "客户端结束，10s 后重启 06 续跑（$before -> $after）"
  sleep 10
done

log "执行最终合并（--merge-only → triples_merged.jsonl）"
$PY --merge-only >> "$LOG" 2>&1
log "编排结束。最终文件: $OUT/triples_merged.jsonl"
