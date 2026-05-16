#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Assemble SFT messages dataset from sampled PMIDs + abstracts + triples.
# 基于采样的 PMID + 摘要 + 三元组，组装成 SFTTrainer 标准的 messages 格式数据集。
"""
输入：
  - sampled_5000_pmids.txt    （03 产物）
  - pmid_to_abstract.jsonl    （01 产物）
  - pmid_to_triples.jsonl     （02 产物）
  - prompts/Triple_prompt_v2_finetune.md  （精简版提示词，整体作为 system 内容）

输出：sft_dataset.jsonl，每行一条样本
  {
    "PMID": "...",
    "messages": [
      {"role": "system",    "content": "<精简提示词>"},
      {"role": "user",      "content": "<abstract 原文>"},
      {"role": "assistant", "content": "<JSON 数组字符串>"}
    ]
  }

注意：assistant 输出剔除 ID1 / ID2 / PMID 字段（推理时不需要），并按 compact 紧凑格式序列化以省 token。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml


def merge_title_abstract(title: str, abstract: str) -> str:
    """与原始 API 调用脚本 Triple_extraction.py:278-282 保持一致：
    title + 空格 + abstract，所有连续空白（空格/换行/制表符）压缩为单个空格。
    """
    title_clean = (title or "").strip()
    abstract_clean = (abstract or "").strip()
    merged = f"{title_clean} {abstract_clean}".strip()
    return re.sub(r"\s+", " ", merged)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="组装 SFTTrainer 标准 messages 训练样本")
    parser.add_argument(
        "--config", "-c",
        default="src/Fine_tuning/configs/data_config.yaml",
        help="数据处理配置 YAML 路径",
    )
    parser.add_argument(
        "--sampled-pmids", default=None,
        help="采样 PMID 列表 txt，留空取 output_dir + files.sampled_pmids",
    )
    parser.add_argument(
        "--pmid-to-abstract", default=None,
        help="PMID 摘要索引 jsonl，留空取 output_dir + files.pmid_to_abstract",
    )
    parser.add_argument(
        "--pmid-to-triples", default=None,
        help="PMID 三元组聚合 jsonl，留空取 output_dir + files.pmid_to_triples",
    )
    parser.add_argument(
        "--prompt", default=None,
        help="精简提示词 md，留空取 inputs.finetune_prompt_md",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="输出 sft_dataset.jsonl，留空取 output_dir + files.sft_dataset",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_paths(args: argparse.Namespace, cfg: dict) -> dict[str, Path]:
    """统一解析所有相关路径"""
    repo_root = Path(__file__).resolve().parents[3]
    out_dir = repo_root / cfg["output_dir"]

    paths = {
        "sampled_pmids":      Path(args.sampled_pmids) if args.sampled_pmids
                              else out_dir / cfg["files"]["sampled_pmids"],
        "pmid_to_abstract":   Path(args.pmid_to_abstract) if args.pmid_to_abstract
                              else out_dir / cfg["files"]["pmid_to_abstract"],
        "pmid_to_triples":    Path(args.pmid_to_triples) if args.pmid_to_triples
                              else out_dir / cfg["files"]["pmid_to_triples"],
        "prompt":             Path(args.prompt) if args.prompt
                              else repo_root / cfg["inputs"]["finetune_prompt_md"],
        "output":             Path(args.output) if args.output
                              else out_dir / cfg["files"]["sft_dataset"],
    }
    paths["output"].parent.mkdir(parents=True, exist_ok=True)
    return paths


def load_sampled_pmids(path: Path) -> set[str]:
    with open(path, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def load_jsonl_index(path: Path, key: str = "PMID") -> dict[str, dict]:
    """把 jsonl 加载为 dict[key -> record]"""
    idx: dict[str, dict] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            idx[str(rec[key])] = rec
    return idx


def strip_triple(triple: dict, keep_source: bool, keep_score: bool) -> dict:
    """剔除内部字段（ID1/ID2/PMID），按配置决定是否保留 source_sentence / score"""
    out = {
        "head":      triple.get("head", ""),
        "head_type": triple.get("head_type", ""),
        "relation":  triple.get("relation", ""),
        "tail":      triple.get("tail", ""),
        "tail_type": triple.get("tail_type", ""),
    }
    if keep_source:
        out["source_sentence"] = triple.get("source_sentence", "")
    if keep_score:
        out["score"] = int(triple.get("score", 0))
    return out


def serialize_triples(triples: list[dict], compact: bool) -> str:
    """把三元组列表序列化为 JSON 数组字符串"""
    if compact:
        return json.dumps(triples, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(triples, ensure_ascii=False)


def main() -> None:
    args = parse_args()
    cfg = load_config(Path(args.config))
    paths = resolve_paths(args, cfg)

    sft_cfg = cfg.get("sft_format", {}) or {}
    compact = bool(sft_cfg.get("compact_json", True))
    keep_source = bool(sft_cfg.get("keep_source_sentence", True))
    keep_score = bool(sft_cfg.get("keep_score", True))

    for k, p in paths.items():
        print(f"[路径] {k:20s} = {p}")

    # 加载提示词
    if not paths["prompt"].exists():
        sys.exit(f"[错误] 精简提示词不存在：{paths['prompt']}")
    system_content = paths["prompt"].read_text(encoding="utf-8").strip()

    # 加载 PMID 列表与索引
    sampled = load_sampled_pmids(paths["sampled_pmids"])
    print(f"[加载] 采样 PMID：{len(sampled):,} 个")

    abstract_idx = load_jsonl_index(paths["pmid_to_abstract"])
    print(f"[加载] 摘要索引：{len(abstract_idx):,} 条")

    triples_idx = load_jsonl_index(paths["pmid_to_triples"])
    print(f"[加载] 三元组索引：{len(triples_idx):,} 个 PMID")

    # 组装样本
    n_written = 0
    n_miss_abstract = 0
    n_miss_triples = 0
    with open(paths["output"], "w", encoding="utf-8", newline="\n") as fout:
        for pmid in sorted(sampled):
            abs_rec = abstract_idx.get(pmid)
            tri_rec = triples_idx.get(pmid)
            if not abs_rec or not abs_rec.get("abstract"):
                n_miss_abstract += 1
                continue
            if not tri_rec or not tri_rec.get("triples"):
                n_miss_triples += 1
                continue

            triples_clean = [
                strip_triple(t, keep_source, keep_score) for t in tri_rec["triples"]
            ]
            assistant_text = serialize_triples(triples_clean, compact=compact)

            # user 内容：title + abstract 合并（与原始 API 调用 Triple_extraction.py 保持一致）
            user_content = merge_title_abstract(
                abs_rec.get("title", ""), abs_rec.get("abstract", "")
            )
            sample = {
                "PMID": pmid,
                "messages": [
                    {"role": "system",    "content": system_content},
                    {"role": "user",      "content": user_content},
                    {"role": "assistant", "content": assistant_text},
                ],
            }
            fout.write(json.dumps(sample, ensure_ascii=False) + "\n")
            n_written += 1

    print(f"\n[完成] 写入 {n_written:,} 条样本 → {paths['output']}")
    if n_miss_abstract:
        print(f"   缺摘要跳过：{n_miss_abstract:,}")
    if n_miss_triples:
        print(f"   缺三元组跳过：{n_miss_triples:,}")


if __name__ == "__main__":
    main()
