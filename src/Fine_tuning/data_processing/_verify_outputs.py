#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Sanity-check outputs of the data processing pipeline.
# 数据处理流水线产物的快速核对工具（仅供本次跑通后人工查阅，不属于流水线正式步骤）。

from __future__ import annotations

import json
import statistics
from pathlib import Path


def main() -> None:
    base = Path("data/Fine_tuning_dataset/training_ready/v1")
    files = sorted(base.glob("*"))
    print("=== training_ready/v1 产物清单 ===")
    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        if f.suffix in (".jsonl", ".txt"):
            with open(f, "r", encoding="utf-8") as fp:
                n_lines = sum(1 for _ in fp)
            print(f"  {f.name:35s}  {size_mb:7.2f} MB   {n_lines:>7,} 行")
        else:
            print(f"  {f.name:35s}  {size_mb:7.2f} MB")

    print("\n=== train.jsonl 第一条样本结构核对 ===")
    with open(base / "train.jsonl", "r", encoding="utf-8") as f:
        s = json.loads(f.readline())
    pmid = s["PMID"]
    print(f"PMID: {pmid}")
    print(f"messages 数: {len(s['messages'])}")
    for m in s["messages"]:
        content = m["content"]
        nl = chr(10)
        preview = content[:120].replace(nl, " ")
        suffix = "..." if len(content) > 120 else ""
        print(f"  [{m['role']:9s}] len={len(content):5d}  | {preview}{suffix}")

    print("\n=== 序列长度粗估（4 字符≈1 token） ===")
    lens: list[int] = []
    with open(base / "train.jsonl", "r", encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            total_chars = sum(len(m["content"]) for m in s["messages"])
            lens.append(total_chars)
    p95 = sorted(lens)[int(len(lens) * 0.95)]
    print(f"  字符长度  min={min(lens)} max={max(lens)} "
          f"mean={int(statistics.mean(lens))} median={int(statistics.median(lens))} p95={p95}")
    print(f"  按 4 char/token 估算  median≈{int(statistics.median(lens)/4)} "
          f"p95≈{int(p95/4)} max≈{int(max(lens)/4)}")


if __name__ == "__main__":
    main()
