#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Split sft_dataset.jsonl into train / val / test by PMID.
# 按 PMID 把 sft_dataset.jsonl 切分为 train / val / test。
"""
输入：sft_dataset.jsonl
输出：train.jsonl / val.jsonl / test.jsonl
比例与种子来自 data_config.yaml 的 split 字段。
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 PMID 切分 sft_dataset 为 train/val/test")
    parser.add_argument(
        "--config", "-c",
        default="src/Fine_tuning/configs/data_config.yaml",
        help="数据处理配置 YAML 路径",
    )
    parser.add_argument(
        "--input", "-i", default=None,
        help="输入 sft_dataset.jsonl，留空取 output_dir + files.sft_dataset",
    )
    parser.add_argument(
        "--output-dir", "-d", default=None,
        help="输出目录，留空取 output_dir",
    )
    parser.add_argument(
        "--seed", "-s", type=int, default=None,
        help="随机种子，留空取 split.random_seed",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    args = parse_args()
    cfg = load_config(Path(args.config))

    repo_root = Path(__file__).resolve().parents[3]
    out_dir = Path(args.output_dir) if args.output_dir else (repo_root / cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    input_path = Path(args.input) if args.input else out_dir / cfg["files"]["sft_dataset"]
    train_path = out_dir / cfg["files"]["train_split"]
    val_path   = out_dir / cfg["files"]["val_split"]
    test_path  = out_dir / cfg["files"]["test_split"]

    split_cfg = cfg["split"]
    r_train, r_val, r_test = split_cfg["train_ratio"], split_cfg["val_ratio"], split_cfg["test_ratio"]
    seed = args.seed if args.seed is not None else split_cfg["random_seed"]

    if abs(r_train + r_val + r_test - 1.0) > 1e-6:
        sys.exit(f"[错误] 切分比例之和必须为 1.0，当前为 {r_train + r_val + r_test}")

    # 读取所有样本到内存（5000 条样本，单条 ~3-5KB → ~25MB，可承受）
    samples = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    print(f"[加载] {len(samples):,} 条样本")

    # 按 PMID 切分（PMID 唯一）
    rng = random.Random(seed)
    rng.shuffle(samples)

    n_total = len(samples)
    n_train = int(round(n_total * r_train))
    n_val   = int(round(n_total * r_val))
    n_test  = n_total - n_train - n_val          # 剩余全给 test，避免舍入误差导致总数对不上

    splits = {
        "train": (train_path, samples[:n_train]),
        "val":   (val_path,   samples[n_train : n_train + n_val]),
        "test":  (test_path,  samples[n_train + n_val :]),
    }

    for name, (path, subset) in splits.items():
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for s in subset:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"[完成] {name:5s}  {len(subset):,} 条 → {path}")

    print(f"\n切分比例：train={n_train/n_total:.2%}  val={n_val/n_total:.2%}  test={n_test/n_total:.2%}（seed={seed}）")


if __name__ == "__main__":
    main()
