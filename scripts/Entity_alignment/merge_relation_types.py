#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Merge specified relation types into a single target relation in JSONL triple files.
将 JSONL 三元组文件中的若干关系类型归并为同一个目标关系类型。

用途：把 u_shaped_association_with / inverted_u_shaped_association_with 归并到 associated_with。
默认不覆盖原文件，输出到带后缀的新文件，便于回溯。
"""

import argparse
import json
import os
from collections import Counter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="将 JSONL 三元组中指定的关系类型归并为同一个目标关系类型（默认 U 型/反 U 型 → associated_with）。"
    )
    parser.add_argument(
        "--input", "-i", nargs="+", required=True,
        help="输入 JSONL 文件路径，可传多个（每行一个三元组 JSON 对象）。"
    )
    parser.add_argument(
        "--output", "-o", nargs="+", default=None,
        help="输出文件路径，可传多个；个数须与 --input 一致。省略时按 --suffix 自动命名。"
    )
    parser.add_argument(
        "--suffix", "-s", default="_Umerged",
        help="未显式指定 --output 时，输出文件名在原名（去扩展名）后追加的后缀（默认：_Umerged）。"
    )
    parser.add_argument(
        "--merge-from", "-f", nargs="+",
        default=["u_shaped_association_with", "inverted_u_shaped_association_with"],
        help="需要被归并的源关系类型列表（默认：u_shaped_association_with inverted_u_shaped_association_with）。"
    )
    parser.add_argument(
        "--merge-to", "-t", default="associated_with",
        help="归并到的目标关系类型（默认：associated_with）。"
    )
    parser.add_argument(
        "--relation-key", "-k", default="relation",
        help="JSON 对象中表示关系类型的字段名（默认：relation）。"
    )
    parser.add_argument(
        "--in-place", action="store_true",
        help="原地覆盖输入文件（默认关闭，输出到新文件以便回溯）。"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="试运行：只统计将被归并的条数，不写任何文件。"
    )
    return parser


def resolve_output_path(in_path: str, suffix: str) -> str:
    """根据输入路径与后缀生成输出路径（保持扩展名）。"""
    root, ext = os.path.splitext(in_path)
    return f"{root}{suffix}{ext}"


def process_file(in_path: str, out_path: str, merge_from: set, merge_to: str,
                 rel_key: str, dry_run: bool) -> dict:
    """处理单个文件，返回统计信息字典。"""
    total = 0          # 总行数
    merged = 0         # 被归并的行数
    per_from = Counter()  # 各源关系命中次数
    rel_after = Counter() # 归并后关系分布（仅统计，便于核对）

    out_lines = []
    with open(in_path, "r", encoding="utf-8") as fin:
        for line in fin:
            stripped = line.strip()
            if not stripped:
                continue
            total += 1
            obj = json.loads(stripped)
            rel = obj.get(rel_key)
            if rel in merge_from:
                per_from[rel] += 1
                obj[rel_key] = merge_to
                merged += 1
            rel_after[obj.get(rel_key)] += 1
            if not dry_run:
                out_lines.append(json.dumps(obj, ensure_ascii=False))

    if not dry_run:
        with open(out_path, "w", encoding="utf-8") as fout:
            fout.write("\n".join(out_lines))
            if out_lines:
                fout.write("\n")

    return {
        "in_path": in_path,
        "out_path": None if dry_run else out_path,
        "total": total,
        "merged": merged,
        "per_from": dict(per_from),
        "target_count_after": rel_after.get(merge_to, 0),
    }


def main() -> None:
    args = build_parser().parse_args()

    # 校验 --output 个数
    if args.output is not None and len(args.output) != len(args.input):
        raise SystemExit(f"--output 个数({len(args.output)})须与 --input 个数({len(args.input)})一致。")

    merge_from = set(args.merge_from)
    print("=" * 60)
    print(f"归并源关系: {sorted(merge_from)}")
    print(f"归并目标关系: {args.merge_to}")
    print(f"关系字段: {args.relation_key} | 原地覆盖: {args.in_place} | 试运行: {args.dry_run}")
    print("=" * 60)

    grand_merged = 0
    for idx, in_path in enumerate(args.input):
        if args.in_place:
            out_path = in_path
        elif args.output is not None:
            out_path = args.output[idx]
        else:
            out_path = resolve_output_path(in_path, args.suffix)

        stat = process_file(in_path, out_path, merge_from, args.merge_to,
                            args.relation_key, args.dry_run)
        grand_merged += stat["merged"]
        print(f"\n[文件] {stat['in_path']}")
        print(f"  总条数: {stat['total']}")
        print(f"  被归并: {stat['merged']}  明细: {stat['per_from']}")
        print(f"  归并后 '{args.merge_to}' 总数: {stat['target_count_after']}")
        if stat["out_path"]:
            print(f"  输出 → {stat['out_path']}")

    print("\n" + "=" * 60)
    print(f"完成。累计归并 {grand_merged} 条。" + ("（试运行，未写文件）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
