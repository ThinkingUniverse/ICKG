#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Build PMID -> abstract index from the merged PubMed JSON.
# 从合并后的 PubMed JSON 构建 PMID -> 摘要 索引，供后续微调数据组装使用。
"""
读取 data/pubmed_output/merge/PubMed_abstract_2016_01_01_2026_03_31.json（约 1.6GB），
以流式方式输出 jsonl：每行 {"PMID": "...", "title": "...", "abstract": "..."}。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import ijson  # 流式 JSON 解析器，避免一次性加载 1.6GB
except ImportError:
    ijson = None

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从合并后的 PubMed JSON 构建 PMID->摘要 索引（流式）"
    )
    parser.add_argument(
        "--config", "-c",
        default="src/Fine_tuning/configs/data_config.yaml",
        help="数据处理配置 YAML 路径（默认：src/Fine_tuning/configs/data_config.yaml）",
    )
    parser.add_argument(
        "--input", "-i", default=None,
        help="输入 PubMed JSON 路径，留空则取配置中的 inputs.pubmed_merged_json",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="输出 jsonl 路径，留空则拼接 output_dir + files.pmid_to_abstract",
    )
    parser.add_argument(
        "--skip-empty-abstract", action="store_true", default=True,
        help="跳过摘要为空的记录（默认开启）",
    )
    parser.add_argument(
        "--no-skip-empty-abstract", dest="skip_empty_abstract", action="store_false",
        help="保留摘要为空的记录",
    )
    parser.add_argument(
        "--progress-every", type=int, default=20000,
        help="每处理 N 条记录打印一次进度（默认：20000）",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> dict:
    """加载 yaml 配置"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_paths(args: argparse.Namespace, cfg: dict) -> tuple[Path, Path]:
    """根据 CLI 与配置解析输入输出路径"""
    repo_root = Path(__file__).resolve().parents[3]   # ICKG 仓库根目录

    input_path = Path(args.input) if args.input else repo_root / cfg["inputs"]["pubmed_merged_json"]
    if args.output:
        output_path = Path(args.output)
    else:
        out_dir = repo_root / cfg["output_dir"]
        output_path = out_dir / cfg["files"]["pmid_to_abstract"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return input_path, output_path


def iter_records_streaming(path: Path):
    """优先使用 ijson 流式解析；否则降级为 json.load 全量加载"""
    if ijson is not None:
        with open(path, "rb") as f:
            for item in ijson.items(f, "item"):
                yield item
    else:
        print("[警告] 未安装 ijson，将一次性加载整个 JSON 文件（可能占用数 GB 内存）", file=sys.stderr)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            yield item


def main() -> None:
    args = parse_args()
    cfg = load_config(Path(args.config))
    input_path, output_path = resolve_paths(args, cfg)

    if not input_path.exists():
        sys.exit(f"[错误] 输入文件不存在：{input_path}")

    print(f"[信息] 输入：{input_path}")
    print(f"[信息] 输出：{output_path}")

    n_total = 0
    n_written = 0
    n_dup = 0
    n_empty = 0
    seen_pmids: set[str] = set()

    with open(output_path, "w", encoding="utf-8", newline="\n") as fout:
        for rec in iter_records_streaming(input_path):
            n_total += 1
            pmid = str(rec.get("PMID", "")).strip()
            abstract = (rec.get("Abstract") or "").strip()
            title = (rec.get("Title") or "").strip()

            if not pmid:
                continue
            if args.skip_empty_abstract and not abstract:
                n_empty += 1
                continue
            if pmid in seen_pmids:
                n_dup += 1
                continue
            seen_pmids.add(pmid)

            out = {"PMID": pmid, "title": title, "abstract": abstract}
            fout.write(json.dumps(out, ensure_ascii=False) + "\n")
            n_written += 1

            if n_total % args.progress_every == 0:
                print(f"  已读 {n_total:,} 条，已写 {n_written:,} 条 ...")

    print(f"\n[完成] 总读 {n_total:,} 条；写入 {n_written:,} 条；"
          f"跳过空摘要 {n_empty:,} 条；去重 {n_dup:,} 条。")
    print(f"[完成] 输出文件：{output_path}")


if __name__ == "__main__":
    main()
