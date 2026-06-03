#!/usr/bin/env bash
# Launch a vLLM OpenAI-compatible server for the merged Baichuan-M2-32B-QLoRA model.
# 启动 vLLM 的 OpenAI 兼容服务，加载合并后的 Baichuan-M2-32B-QLoRA(merged) 模型，供三元组抽取推理。
#
# 【在远程服务器执行】建议放进 tmux 或用 nohup 后台跑：
#   tmux new -s vllm
#   bash scripts/vllm_inference/02_serve_vllm.sh
#   # 或： nohup bash scripts/vllm_inference/02_serve_vllm.sh > log/vllm_serve.log 2>&1 &
#
# 所有参数都可用环境变量覆盖，例如：
#   PORT=8801 MAX_MODEL_LEN=8192 GPU_MEM_UTIL=0.95 bash scripts/vllm_inference/02_serve_vllm.sh
#
# 🔴 对齐铁律：本服务只提供 /v1/completions 原样推理，客户端(03)自己用 tokenizer 渲染 prompt，
#    因此【绝不要】在这里加 --reasoning-parser / --enable-reasoning / 任何 thinking 相关开关，
#    否则会把模型推入训练里没见过的 <think> 分布（详见 .planning/baichuan-qlora 评估报告 §3.6）。
set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,24p' "$0"
  exit 0
fi

# ---- 可配置参数（环境变量覆盖）----
MODEL_DIR="${MODEL_DIR:-models/Baichuan-M2-32B-QLoRA-v1/merged}"  # 合并后的完整权重目录
SERVED_NAME="${SERVED_NAME:-baichuan-m2-qlora}"                   # 对外模型名（客户端 --model 用它）
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8801}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"        # prompt(≤4.6k)+completion(≤2.6k) 足够；越小每序列 KV 越省、并发越高
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.95}"          # 单卡 A100 80G：权重~62G，尽量榨干显存给 KV cache
MAX_NUM_SEQS="${MAX_NUM_SEQS:-256}"           # 最大并发序列数；与客户端 --concurrency 配合，压测后调
DTYPE="${DTYPE:-bfloat16}"
KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-}"          # 置 fp8 可翻倍 KV 容量提并发（压测对比质量后再开）
EXTRA_ARGS="${EXTRA_ARGS:-}"                  # 透传给 vllm serve 的额外参数

echo "[vllm] MODEL_DIR=$MODEL_DIR  SERVED_NAME=$SERVED_NAME  PORT=$PORT"
echo "[vllm] MAX_MODEL_LEN=$MAX_MODEL_LEN  GPU_MEM_UTIL=$GPU_MEM_UTIL  MAX_NUM_SEQS=$MAX_NUM_SEQS  KV_CACHE_DTYPE=${KV_CACHE_DTYPE:-default}"

# --enable-prefix-caching：1,919 token 的 system 提示词在 68 万次请求里完全相同，
#   前缀缓存可复用其 KV，显著降低重复 prefill 开销 → 吞吐提升的关键优化。
# --disable-log-requests：高并发下关闭逐请求日志，减少 CPU/IO 开销。
exec vllm serve "$MODEL_DIR" \
  --served-model-name "$SERVED_NAME" \
  --host "$HOST" --port "$PORT" \
  --dtype "$DTYPE" \
  --max-model-len "$MAX_MODEL_LEN" \
  --gpu-memory-utilization "$GPU_MEM_UTIL" \
  --max-num-seqs "$MAX_NUM_SEQS" \
  --enable-prefix-caching \
  --disable-log-requests \
  --trust-remote-code \
  ${KV_CACHE_DTYPE:+--kv-cache-dtype "$KV_CACHE_DTYPE"} \
  ${EXTRA_ARGS}
