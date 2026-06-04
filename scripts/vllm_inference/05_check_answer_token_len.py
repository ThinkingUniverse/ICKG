#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Analyze the assistant (answer) token-length distribution in the SFT training set,
# to verify training targets were not heavily truncated at max_length.
# 统计 SFT 训练集中 assistant(答案) 的 token 长度分布，核验训练目标是否被 max_length 大量截断。
import argparse
import json

import numpy as np
from transformers import AutoTokenizer


def parse_args():
    p = argparse.ArgumentParser(description="统计 SFT 训练集 assistant 答案 token 长度分布，核验是否被 max_length 截断")
    p.add_argument("--sft", "-i", default="data/Fine_tuning_dataset/training_ready/v1/sft_dataset.jsonl",
                   help="SFT 数据路径（jsonl，每行含 messages）")
    p.add_argument("--tokenizer", "-t", default="models/hf/Baichuan-M2-32B",
                   help="tokenizer 目录（默认 base，词表与 merged 一致）")
    p.add_argument("--max-length", "-m", type=int, default=5120, help="训练时的 max_length（默认 5120）")
    return p.parse_args()


def report(name, a):
    print(f"\n[{name}] n={len(a)}  min={int(a.min())}  mean={a.mean():.0f}  median={int(np.median(a))}  "
          f"p90={np.percentile(a,90):.0f}  p95={np.percentile(a,95):.0f}  p99={np.percentile(a,99):.0f}  max={int(a.max())}")


def main():
    args = parse_args()
    tok = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)
    ans_lens, full_lens = [], []
    with open(args.sft, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            ms = o["messages"]
            assistant = [m["content"] for m in ms if m["role"] == "assistant"][0]
            ans_lens.append(len(tok(assistant, add_special_tokens=False)["input_ids"]))
            full = tok.apply_chat_template(ms, tokenize=True, add_generation_prompt=False)
            full_lens.append(len(full))
    ans = np.array(ans_lens)
    full = np.array(full_lens)
    report("assistant 答案 token 长度", ans)
    for thr in (2326, 2560, 3072, 4096):
        c = int((ans >= thr).sum())
        print(f"  答案 >= {thr}: {c} 篇 ({c/len(ans)*100:.2f}%)")
    report("full(system+user+assistant) token 长度", full)
    over = int((full > args.max_length).sum())
    print(f"\n*** full > max_length({args.max_length}) 的样本（=训练时被截断、答案尾部丢失）: {over} 篇 ({over/len(full)*100:.2f}%) ***")
    if over > 0:
        cut = full[full > args.max_length] - args.max_length
        print(f"    被切掉的 token 数: mean={cut.mean():.0f}  median={int(np.median(cut))}  max={int(cut.max())}")


if __name__ == "__main__":
    main()
