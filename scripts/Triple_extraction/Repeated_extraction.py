"""
功能：检测 JSONL 文件中同一 PMID 是否被非连续重复提取。
Function: Detect whether the same PMID appears in multiple non-contiguous segments in a JSONL file.

本脚本按连续块统计 PMID 的出现段数，若同一 PMID 后续再次出现且中间被其他 PMID 隔开，则判定为重复提取。
This script counts contiguous PMID segments. If the same PMID appears again later with other PMIDs in between, it is treated as repeated extraction.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


@dataclass
class Segment:
	pmid: str
	start_line: int
	end_line: int
	record_count: int


def parse_pmids_arg(pmids_arg: Optional[str]) -> Optional[Set[str]]:
	if not pmids_arg:
		return None
	pmids = {item.strip() for item in pmids_arg.split(",") if item.strip()}
	return pmids or None


def parse_pmids_file(pmids_file: Optional[Path]) -> Optional[Set[str]]:
	if not pmids_file:
		return None
	pmids: Set[str] = set()
	with pmids_file.open("r", encoding="utf-8") as f:
		for line in f:
			item = line.strip()
			if item:
				pmids.add(item)
	return pmids or None


def merge_target_pmids(pmids_arg: Optional[str], pmids_file: Optional[Path]) -> Optional[Set[str]]:
	pmids_from_arg = parse_pmids_arg(pmids_arg)
	pmids_from_file = parse_pmids_file(pmids_file)

	if pmids_from_arg is None and pmids_from_file is None:
		return None
	if pmids_from_arg is None:
		return pmids_from_file
	if pmids_from_file is None:
		return pmids_from_arg
	return pmids_from_arg.union(pmids_from_file)


def iter_segments(jsonl_path: Path) -> Iterable[Segment]:
	current_pmid: Optional[str] = None
	start_line: Optional[int] = None
	end_line: Optional[int] = None
	count = 0

	with jsonl_path.open("r", encoding="utf-8") as f:
		for lineno, raw_line in enumerate(f, start=1):
			line = raw_line.strip()
			if not line:
				continue

			try:
				record = json.loads(line)
			except json.JSONDecodeError as exc:
				raise ValueError(f"Line {lineno} is not valid JSON: {exc}") from exc

			if "PMID" not in record:
				raise ValueError(f"Line {lineno} has no 'PMID' field")

			pmid = str(record["PMID"]).strip()
			if not pmid:
				raise ValueError(f"Line {lineno} has an empty PMID")

			if current_pmid is None:
				current_pmid = pmid
				start_line = lineno
				end_line = lineno
				count = 1
				continue

			if pmid == current_pmid:
				end_line = lineno
				count += 1
				continue

			yield Segment(
				pmid=current_pmid,
				start_line=start_line if start_line is not None else lineno,
				end_line=end_line if end_line is not None else lineno,
				record_count=count,
			)

			current_pmid = pmid
			start_line = lineno
			end_line = lineno
			count = 1

	if current_pmid is not None and start_line is not None and end_line is not None:
		yield Segment(
			pmid=current_pmid,
			start_line=start_line,
			end_line=end_line,
			record_count=count,
		)


def find_repeated_pmids(jsonl_path: Path) -> Dict[str, List[Segment]]:
	pmid_segments: Dict[str, List[Segment]] = {}
	for segment in iter_segments(jsonl_path):
		pmid_segments.setdefault(segment.pmid, []).append(segment)

	return {pmid: segs for pmid, segs in pmid_segments.items() if len(segs) > 1}


def print_summary(repeated: Dict[str, List[Segment]], target_pmids: Optional[Set[str]]) -> None:
	if target_pmids is not None:
		filtered: Dict[str, List[Segment]] = {
			pmid: repeated[pmid] for pmid in target_pmids if pmid in repeated
		}
	else:
		filtered = repeated

	if not filtered:
		if target_pmids:
			print("指定 PMID 中未发现非连续重复提取。")
		else:
			print("未发现非连续重复提取。")
		return

	print(f"发现 {len(filtered)} 个 PMID 存在非连续重复提取：")
	for pmid in sorted(filtered):
		segs = filtered[pmid]
		print(f"\nPMID: {pmid} (分段数: {len(segs)})")
		for idx, seg in enumerate(segs, start=1):
			print(
				f"  段{idx}: 行 {seg.start_line}-{seg.end_line}, "
				f"三元组数 {seg.record_count}"
			)


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description="检测 JSONL 中 PMID 是否出现非连续重复提取（多个分段出现）"
	)
	parser.add_argument(
		"--input",
		type=Path,
		default=Path("data/Fine_tuning_dataset/triples_baichuan_m3_plus.jsonl"),
		help="输入 JSONL 文件路径",
	)
	parser.add_argument(
		"--pmids",
		type=str,
		default=None,
		help="只检查这些 PMID，逗号分隔，例如: 29249001,41347977",
	)
	parser.add_argument(
		"--pmids-file",
		type=Path,
		default=None,
		help="每行一个 PMID 的文本文件，用于筛选检查范围",
	)
	return parser


def main() -> None:
	parser = build_parser()
	args = parser.parse_args()

	if not args.input.exists():
		raise FileNotFoundError(f"Input file not found: {args.input}")

	target_pmids = merge_target_pmids(args.pmids, args.pmids_file)
	repeated = find_repeated_pmids(args.input)
	print_summary(repeated, target_pmids)


if __name__ == "__main__":
	main()
