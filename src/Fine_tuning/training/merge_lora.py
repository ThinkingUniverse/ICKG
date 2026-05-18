#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Merge LoRA adapter back into the base model and save a standalone bfloat16 checkpoint.
# 把训练好的 LoRA 适配器合并回基础模型，保存为可独立加载的 bfloat16 完整权重。
"""
注意：4bit 量化下不能直接 merge_and_unload，需要先以 bfloat16 全精度重新加载基础模型，
然后挂上 LoRA 适配器并合并，最后保存。该过程显存占用较高（32B × 2 bytes ≈ 64GB CPU+GPU 混合）。
若单机显存有限，可在 CPU 上执行（速度较慢但可行）。

启动示例：
    conda activate lckg
    python src/Fine_tuning/training/merge_lora.py \
        --config src/Fine_tuning/configs/train_config.yaml \
        --device cpu
"""

from __future__ import annotations

# ============================================================
# 与 train_qlora.py 一致：先从 yaml env 段写 os.environ，
# 再 import HF 库，这样 HF_ENDPOINT / HF_HOME 生效。
# ============================================================
import os
import sys
from pathlib import Path

import yaml


def _bootstrap_env_from_config() -> None:
    cfg_path = None
    for flag in ("--config", "-c"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                cfg_path = sys.argv[i + 1]
                break
    if not cfg_path or not Path(cfg_path).exists():
        return
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            env_block = (yaml.safe_load(f).get("env") or {})
    except Exception:
        return
    for k, v in env_block.items():
        if v is None:
            continue
        os.environ.setdefault(k, str(v))


_bootstrap_env_from_config()

import argparse

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把 LoRA 适配器合并到基础模型并另存完整权重")
    parser.add_argument(
        "--config", "-c", required=True,
        help="训练配置 yaml 路径（与 train_qlora.py 共用）",
    )
    parser.add_argument(
        "--adapter-dir", default=None,
        help="LoRA 适配器目录，留空取 yaml 的 adapter_dir",
    )
    parser.add_argument(
        "--output-dir", "-o", default=None,
        help="合并后权重输出目录，留空取 yaml 的 merged_dir",
    )
    parser.add_argument(
        "--base-model", default=None,
        help="基础模型 HF 名或本地路径，留空取 yaml 的 model.name_or_path",
    )
    parser.add_argument(
        "--device", choices=["auto", "cpu", "cuda"], default="auto",
        help="加载基础模型使用的设备（默认 auto；显存不足时强制 cpu）",
    )
    parser.add_argument(
        "--torch-dtype", choices=["bfloat16", "float16"], default="bfloat16",
        help="合并时使用的精度（默认 bfloat16）",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    args = parse_args()
    cfg = load_config(Path(args.config))
    repo_root = Path(__file__).resolve().parents[3]

    base_model = args.base_model or cfg["model"]["name_or_path"]
    adapter_dir = Path(args.adapter_dir) if args.adapter_dir else repo_root / cfg["adapter_dir"]
    output_dir = Path(args.output_dir) if args.output_dir else repo_root / cfg["merged_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    if not adapter_dir.exists():
        sys.exit(f"[错误] LoRA 适配器目录不存在：{adapter_dir}")

    dtype = torch.bfloat16 if args.torch_dtype == "bfloat16" else torch.float16
    device_map = args.device if args.device != "auto" else "auto"

    print(f"[加载] 基础模型：{base_model}  dtype={args.torch_dtype}  device_map={device_map}")
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        dtype=dtype,                                # transformers 4.45+ 使用 dtype 替代 torch_dtype
        device_map=device_map,
        trust_remote_code=cfg["model"].get("trust_remote_code", True),
    )

    print(f"[加载] LoRA 适配器：{adapter_dir}")
    model = PeftModel.from_pretrained(base, str(adapter_dir))

    print("[合并] merge_and_unload ...")
    model = model.merge_and_unload()

    print(f"[保存] → {output_dir}")
    model.save_pretrained(str(output_dir), safe_serialization=True)

    tokenizer = AutoTokenizer.from_pretrained(
        str(adapter_dir), trust_remote_code=cfg["model"].get("trust_remote_code", True),
    )
    tokenizer.save_pretrained(str(output_dir))

    print(f"[完成] 完整权重已保存：{output_dir}")
    print("       可直接用 AutoModelForCausalLM.from_pretrained(<dir>, trust_remote_code=True) 加载推理。")


if __name__ == "__main__":
    main()
