#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Filter out already-extracted PMIDs from the full PubMed corpus and split the
# remaining articles into vLLM inference input shards (one {PMID, user_content} per line).
# 从全量 PubMed 文章中剔除「已提取」（按 triples_usage.jsonl 的 PMID）的文章，
# 把剩余文章整理成 vLLM 推理输入分片（每行一个 {PMID, user_content}），供 03_extract_client.py 消费。
"""
流程：
  1. 读入若干「已提取」清单（默认两批 triples_usage.jsonl，每行含 PMID），构成 done 集合；
  2. 流式（ijson）遍历全量文章 JSON（对象数组，约 1.65GB，避免一次性载入内存）；
  3. 剔除 PMID ∈ done 的文章，剩余文章按 title+abstract 合并成 user_content
     （与训练 04_build_sft_dataset.py 完全一致：strip + 单空格、连续空白压成一个空格）；
  4. 以 round-robin 方式均匀写入 N 个分片 JSONL；
  5. 输出 manifest.json 记录各项计数，便于核对「剩余约 68 万」。

注意：分片里只放 {PMID, user_content}，system 提示词在推理客户端侧拼接，
      以保证「不传 thinking_mode」的对齐铁律由客户端统一把关。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import ijson  # 流式 JSON 解析，避免 1.65GB 一次性载入
except ImportError:
    ijson = None


def merge_title_abstract(title: str, abstract: str) -> str:
    """与 04_build_sft_dataset.py 一致：title.strip() + 空格 + abstract.strip()，连续空白压成单空格。"""
    title_clean = (title or "").strip()
    abstract_clean = (abstract or "").strip()
    merged = f"{title_clean} {abstract_clean}".strip()
    return re.sub(r"\s+", " ", merged)


def load_done_pmids(usage_paths, txt_paths, pmid_field: str) -> set:
    """从 jsonl（取 pmid_field）与纯文本（每行一个 PMID）清单合并出已提取 PMID 集合。"""
    done = set()
    for p in usage_paths or []:
        path = Path(p)
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                done.add(str(obj[pmid_field]))
        print(f"[done] 载入 {path}  累计唯一 PMID={len(done)}")
    for p in txt_paths or []:
        path = Path(p)
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                pid = line.strip()
                if pid:
                    done.add(pid)
        print(f"[done] 载入 {path}  累计唯一 PMID={len(done)}")
    return done


def iter_articles(full_json_path: str):
    """流式产出全量文章对象；优先 ijson，缺失则回退 json.load（吃内存）。"""
    if ijson is not None:
        with open(full_json_path, "rb") as f:
            for obj in ijson.items(f, "item"):
                yield obj
    else:
        print("[警告] 未安装 ijson，回退一次性 json.load（可能吃数 GB 内存）", file=sys.stderr)
        with open(full_json_path, "r", encoding="utf-8") as f:
            for obj in json.load(f):
                yield obj


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="剔除已提取 PMID 并把剩余 PubMed 文章分片成 vLLM 推理输入")
    p.add_argument("--full-json", "-f",
                   default="data/pubmed_output/merge/PubMed_abstract_2016_01_01_2026_03_31.json",
                   help="全量文章 JSON 路径（对象数组，每篇含 PMID/Title/Abstract）")
    p.add_argument("--done-usage", "-d", nargs="+",
                   default=[
                       "data/Fine_tuning_dataset/First_batch/triples_usage.jsonl",
                       "data/Fine_tuning_dataset/Second_batch/triples_usage.jsonl",
                   ],
                   help="已提取清单 jsonl（每行含 PMID 字段），可多个，默认两批 triples_usage.jsonl")
    p.add_argument("--done-pmid-txt", nargs="*", default=[],
                   help="可选：额外的纯文本已提取清单（每行一个 PMID）")
    p.add_argument("--output-dir", "-o", default="data/vllm_inference/input_shards",
                   help="分片输出目录（默认 data/vllm_inference/input_shards）")
    p.add_argument("--num-shards", "-n", type=int, default=20, help="分片数量（默认 20）")
    p.add_argument("--shard-prefix", default="shard", help="分片文件名前缀（默认 shard）")
    p.add_argument("--pmid-field", default="PMID", help="文章 PMID 字段名（默认 PMID）")
    p.add_argument("--done-pmid-field", default="PMID", help="已提取清单中 PMID 字段名（默认 PMID）")
    p.add_argument("--title-field", default="Title", help="标题字段名（默认 Title）")
    p.add_argument("--abstract-field", default="Abstract", help="摘要字段名（默认 Abstract）")
    p.add_argument("--min-chars", type=int, default=1,
                   help="user_content 最小字符数，低于则跳过并计入 skipped_empty（默认 1）")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    done = load_done_pmids(args.done_usage, args.done_pmid_txt, args.done_pmid_field)
    print(f"[done] 已提取唯一 PMID 合计 = {len(done)}")

    # 打开 N 个分片句柄，round-robin 均匀写入
    width = max(3, len(str(args.num_shards - 1)))
    shard_paths = [out_dir / f"{args.shard_prefix}_{i:0{width}d}.jsonl" for i in range(args.num_shards)]
    handles = [p.open("w", encoding="utf-8") for p in shard_paths]
    shard_counts = [0] * args.num_shards

    total = kept = skipped_done = skipped_empty = dup = 0
    seen = set()
    try:
        for obj in iter_articles(args.full_json):
            total += 1
            pmid = str(obj.get(args.pmid_field, "") or "")
            if pmid in seen:
                dup += 1
                continue
            seen.add(pmid)
            if pmid in done:
                skipped_done += 1
                continue
            user_content = merge_title_abstract(
                str(obj.get(args.title_field, "") or ""),
                str(obj.get(args.abstract_field, "") or ""),
            )
            if len(user_content) < args.min_chars:
                skipped_empty += 1
                continue
            idx = kept % args.num_shards
            handles[idx].write(json.dumps({"PMID": pmid, "user_content": user_content},
                                          ensure_ascii=False) + "\n")
            shard_counts[idx] += 1
            kept += 1
            if total % 100000 == 0:
                print(f"  ... 已扫描 {total}  保留 {kept}  剔除已提取 {skipped_done}")
    finally:
        for h in handles:
            h.close()

    manifest = {
        "full_json": args.full_json,
        "done_sources": list(args.done_usage) + list(args.done_pmid_txt),
        "total_scanned": total,
        "total_unique_pmid": len(seen),
        "duplicate_pmid": dup,
        "done_pmids": len(done),
        "skipped_already_done": skipped_done,
        "skipped_empty": skipped_empty,
        "kept_remaining": kept,
        "num_shards": args.num_shards,
        "shards": [
            {"file": shard_paths[i].name, "count": shard_counts[i]}
            for i in range(args.num_shards)
        ],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 分片完成 =====")
    print(f"全量扫描            : {total}")
    print(f"全量唯一 PMID       : {len(seen)} （重复 {dup}）")
    print(f"剔除已提取          : {skipped_done}")
    print(f"跳过空 user_content : {skipped_empty}")
    print(f"保留待推理          : {kept}  → {args.num_shards} 片，每片约 {kept // max(1, args.num_shards)}")
    print(f"分片目录            : {out_dir}")
    print(f"清单                : {out_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
