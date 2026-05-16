#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Use HF tokenizer to estimate real token lengths of SFT samples.
# 用真实 HF tokenizer 估算样本的真实 token 长度，校准 max_seq_length 设置。
"""
默认使用 Qwen2.5 tokenizer（Baichuan-M2-32B 基于 Qwen2.5/3 架构，token 数量级一致；
若已下载 baichuan-inc/Baichuan-M2-32B 可改 --tokenizer）。
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from transformers import AutoTokenizer


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="用 HF tokenizer 估算 SFT 样本真实 token 长度")
    p.add_argument(
        "--tokenizer", "-t", default="Qwen/Qwen2.5-7B",
        help="HF tokenizer 名（默认 Qwen/Qwen2.5-7B，Baichuan-M2 同系架构）",
    )
    p.add_argument(
        "--input", "-i", default="data/Fine_tuning_dataset/training_ready/v1/train.jsonl",
        help="待估算的 jsonl 路径",
    )
    p.add_argument(
        "--sample-n", "-n", type=int, default=200,
        help="抽样估算的样本数（默认 200，平衡速度与精度）",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    print(f"[加载] tokenizer = {args.tokenizer}")
    tok = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)

    print(f"[读取] {args.input}（抽前 {args.sample_n} 条）")
    samples: list[dict] = []
    with open(args.input, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= args.sample_n:
                break
            samples.append(json.loads(line))

    sys_lens, usr_lens, asi_lens, tot_lens = [], [], [], []
    for s in samples:
        msgs = s["messages"]
        # 直接 apply_chat_template 得到训练实际使用的完整序列
        full = tok.apply_chat_template(msgs, tokenize=True, add_generation_prompt=False)
        tot_lens.append(len(full))
        # 各 role 单独 token 数
        for m in msgs:
            ids = tok.encode(m["content"], add_special_tokens=False)
            if m["role"] == "system":
                sys_lens.append(len(ids))
            elif m["role"] == "user":
                usr_lens.append(len(ids))
            elif m["role"] == "assistant":
                asi_lens.append(len(ids))

    def stat(name: str, arr: list[int]) -> None:
        a = sorted(arr)
        print(f"  {name:12s}  min={a[0]:5d}  mean={int(statistics.mean(a)):5d}  "
              f"median={a[len(a)//2]:5d}  p95={a[int(len(a)*0.95)]:5d}  max={a[-1]:5d}")

    print("\n=== Token 长度统计（基于真实 tokenizer） ===")
    stat("system",    sys_lens)
    stat("user",      usr_lens)
    stat("assistant", asi_lens)
    stat("apply_chat_template(total)", tot_lens)

    print("\n=== max_seq_length 建议 ===")
    p95 = sorted(tot_lens)[int(len(tot_lens) * 0.95)]
    print(f"  median≈{statistics.median(tot_lens):.0f}  p95≈{p95}  max≈{max(tot_lens)}")
    suggested = 1024 * ((p95 // 1024) + 1)            # 向上取 1024 倍数
    print(f"  建议 max_seq_length（覆盖 p95 并留余量）：{suggested}")
    print(f"  若想覆盖 99%+ 样本：{1024 * ((max(tot_lens) // 1024) + 1)}")


if __name__ == "__main__":
    main()
