#!/usr/bin/env bash
# Stress-test the running vLLM server with evalscope to find the concurrency sweet spot.
# 用 evalscope 对已启动的 vLLM 服务做并发压测，找吞吐甜点、估算全量耗时与费用（决定充值额度）。
#
# 【在远程服务器执行，且 02_serve_vllm.sh 已起服务后再跑】
# 依赖：建议单独虚拟环境，避免污染 vllm_env：
#   conda create -n evalscope python=3.12 -y && conda activate evalscope
#   pip install 'evalscope[perf]' -U
#
# 用法：
#   bash scripts/vllm_inference/04_perf_evalscope.sh
#   PARALLEL="32 64 128" NUMBER="256 512 1024" bash scripts/vllm_inference/04_perf_evalscope.sh
#
# 说明：用 random 合成数据，prompt 长度对齐真实分布(3.5k~4.6k)、输出对齐(≤2.6k)，
#   --extra-args ignore_eos=true 强制吐满 max-tokens → 量出「最坏情况」解码吞吐（保守估时）。
#   ⚠️ 这是合成压测，用于「调并发参数」；真实端到端吞吐以 03_extract_client.py --limit 的 pilot 为准。
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,22p' "$0"
  exit 0
fi

SERVED_NAME="${SERVED_NAME:-baichuan-m2-qlora}"
URL="${URL:-http://127.0.0.1:8801/v1/chat/completions}"
TOKENIZER="${TOKENIZER:-models/Baichuan-M2-32B-QLoRA-v1/merged}"
PARALLEL="${PARALLEL:-8 16 32 64 128}"     # 并发档位（逐档对比吞吐/延迟）
NUMBER="${NUMBER:-64 128 256 512 1024}"    # 各档发起的请求数（与 PARALLEL 一一对应）
MAX_TOKENS="${MAX_TOKENS:-2560}"
MIN_TOKENS="${MIN_TOKENS:-512}"
MIN_PROMPT="${MIN_PROMPT:-3500}"
MAX_PROMPT="${MAX_PROMPT:-4600}"

echo "[evalscope] URL=$URL  MODEL=$SERVED_NAME  PARALLEL=[$PARALLEL]  NUMBER=[$NUMBER]"

evalscope perf \
  --parallel ${PARALLEL} \
  --number ${NUMBER} \
  --model "$SERVED_NAME" \
  --url "$URL" \
  --api openai \
  --dataset random \
  --max-tokens "$MAX_TOKENS" \
  --min-tokens "$MIN_TOKENS" \
  --prefix-length 0 \
  --min-prompt-length "$MIN_PROMPT" \
  --max-prompt-length "$MAX_PROMPT" \
  --tokenizer-path "$TOKENIZER" \
  --extra-args '{"ignore_eos": true}'
