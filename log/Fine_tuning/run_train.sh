#!/usr/bin/env bash
# Launcher for 3-epoch Baichuan-M2-32B QLoRA training (run inside tmux).
# 在 tmux 内启动 3 epoch 的 Baichuan-M2-32B QLoRA 正式训练。
set -o pipefail
source /root/miniconda3/etc/profile.d/conda.sh
conda activate ickg
cd /root/ICKG
mkdir -p log/Fine_tuning
TS=$(date +%Y%m%d_%H%M%S)
LOG=log/Fine_tuning/train_${TS}.log
echo "[launch] $(date '+%F %T') 启动 3-epoch QLoRA 训练 → ${LOG}"
echo "[env] python=$(which python)"
python src/Fine_tuning/training/train_qlora.py   --config src/Fine_tuning/configs/train_config.yaml 2>&1 | tee "${LOG}"
echo "[done] python_exit=${PIPESTATUS[0]} at $(date '+%F %T')" | tee -a "${LOG}"
