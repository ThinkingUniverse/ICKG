#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Aggregate triples by PMID and apply relation merge map.
# 把第二批三元组按 PMID 聚合，并按配置把极低频关系映射到兜底关系。
"""
输入：第二批清洗后三元组 jsonl（每行一个三元组）
输出：每行一个 PMID 的聚合 jsonl
  {"PMID": "...", "n_triples": N, "triples": [{head, head_type, relation, tail, tail_type, source_sentence, score}, ...]}

  - 三元组在 PMID 内按 (score 降序, ID2 升序) 排序
  - 关系映射规则来自 data_config.yaml 的 relation_merge_map
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 PMID 聚合三元组并执行关系映射")
    parser.add_argument(
        "--config", "-c",
        default="src/Fine_tuning/configs/data_config.yaml",
        help="数据处理配置 YAML 路径",
    )
    parser.add_argument(
        "--input", "-i", default=None,
        help="输入三元组 jsonl，留空则取配置中的 inputs.second_batch_triples_jsonl",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="输出聚合 jsonl，留空则拼接 output_dir + files.pmid_to_triples",
    )
    parser.add_argument(
        "--progress-every", type=int, default=50000,
        help="每处理 N 条三元组打印一次进度（默认：50000）",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict:
    """加载 yaml 配置"""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_paths(args: argparse.Namespace, cfg: dict) -> tuple[Path, Path]:
    """解析输入输出路径"""
    repo_root = Path(__file__).resolve().parents[3]

    input_path = Path(args.input) if args.input else repo_root / cfg["inputs"]["second_batch_triples_jsonl"]
    if args.output:
        output_path = Path(args.output)
    else:
        out_dir = repo_root / cfg["output_dir"]
        output_path = out_dir / cfg["files"]["pmid_to_triples"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return input_path, output_path


def safe_int(value, default: int = 0) -> int:
    """把 score / ID2 等字段安全转 int，失败返回 default"""
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def main() -> None:
    args = parse_args()
    cfg = load_config(Path(args.config))
    input_path, output_path = resolve_paths(args, cfg)
    relation_map: dict[str, str] = cfg.get("relation_merge_map") or {}

    if not input_path.exists():
        sys.exit(f"[错误] 输入文件不存在：{input_path}")

    print(f"[信息] 输入：{input_path}")
    print(f"[信息] 输出：{output_path}")
    print(f"[信息] 关系映射规则：{relation_map}")

    pmid2triples: dict[str, list[dict]] = defaultdict(list)
    n_read = 0
    n_remapped = 0
    n_invalid = 0

    with open(input_path, "r", encoding="utf-8") as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                n_invalid += 1
                continue

            n_read += 1
            pmid = str(rec.get("PMID", "")).strip()
            if not pmid:
                n_invalid += 1
                continue

            relation = rec.get("relation", "")
            if relation in relation_map:
                relation = relation_map[relation]
                n_remapped += 1

            triple = {
                "head":            rec.get("head", ""),
                "head_type":       rec.get("head_type", ""),
                "relation":        relation,
                "tail":            rec.get("tail", ""),
                "tail_type":       rec.get("tail_type", ""),
                "source_sentence": rec.get("source_sentence", ""),
                "score":           safe_int(rec.get("score"), 0),
                "_id2":            safe_int(rec.get("ID2"), 9999999),  # 内部排序键，输出前剔除
            }
            pmid2triples[pmid].append(triple)

            if n_read % args.progress_every == 0:
                print(f"  已读 {n_read:,} 条三元组，已聚合 {len(pmid2triples):,} 个 PMID ...")

    n_pmids = len(pmid2triples)
    print(f"\n[聚合] 共 {n_pmids:,} 个 PMID；读入 {n_read:,} 条三元组；"
          f"映射关系 {n_remapped:,} 条；非法记录 {n_invalid:,} 条。")

    # 写出：每行一个 PMID
    n_written_triples = 0
    with open(output_path, "w", encoding="utf-8", newline="\n") as fout:
        for pmid, triples in pmid2triples.items():
            triples.sort(key=lambda t: (-t["score"], t["_id2"]))
            cleaned = [{k: v for k, v in t.items() if k != "_id2"} for t in triples]
            out = {"PMID": pmid, "n_triples": len(cleaned), "triples": cleaned}
            fout.write(json.dumps(out, ensure_ascii=False) + "\n")
            n_written_triples += len(cleaned)

    print(f"[完成] 共写出 {n_pmids:,} 个 PMID（{n_written_triples:,} 条三元组）→ {output_path}")


if __name__ == "__main__":
    main()
