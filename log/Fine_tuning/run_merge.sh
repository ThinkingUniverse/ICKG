#!/usr/bin/env bash
# Launcher: merge LoRA adapter into base model -> merged bf16 (run inside tmux).
# 在 tmux 内把 LoRA adapter 合并进基座，另存 merged bf16 完整权重。
set -o pipefail
source /root/miniconda3/etc/profile.d/conda.sh
conda activate ickg
cd /root/ICKG
mkdir -p log/Fine_tuning
TS=$(date +%Y%m%d_%H%M%S)
LOG=log/Fine_tuning/merge_${TS}.log
echo "[merge] $(date '+%F %T') 开始合并 LoRA→merged bf16 → ${LOG}"
python src/Fine_tuning/training/merge_lora.py   --config src/Fine_tuning/configs/train_config.yaml   --test-after-merge 2 2>&1 | tee "${LOG}"
echo "[done] merge_exit=${PIPESTATUS[0]} at $(date '+%F %T')" | tee -a "${LOG}"
