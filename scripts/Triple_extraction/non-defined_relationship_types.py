"""Compare extracted triple types/relations against predefined schema in prompt.

This script reads:
1) A JSONL file where each line is a triple record.
2) A markdown prompt file containing:
   - Predefined Entity Types table
   - Predefined Relation Types table

It reports unique head_type, tail_type, entity_type union, relation, and
bidirectional set differences against predefined types.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_JSONL = Path(
	r"C:\Users\Administrator\Desktop\ICKG\data\Fine_tuning_dataset\del\tmp\sample10_triples_baichuan_m3_plus.jsonl"
)
DEFAULT_PROMPT = Path(r"C:\Users\Administrator\Desktop\ICKG\prompts\Triple_prompt.md")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
	rows: list[dict[str, Any]] = []
	with path.open("r", encoding="utf-8") as f:
		for idx, line in enumerate(f, start=1):
			line = line.strip()
			if not line:
				continue
			try:
				obj = json.loads(line)
			except json.JSONDecodeError as exc:
				raise ValueError(f"Invalid JSON at line {idx} in {path}: {exc}") from exc
			if not isinstance(obj, dict):
				raise ValueError(f"Line {idx} in {path} is not a JSON object")
			rows.append(obj)
	return rows


def parse_predefined_tables(prompt_path: Path) -> tuple[set[str], set[str]]:
	text = prompt_path.read_text(encoding="utf-8")
	lines = text.splitlines()

	entity_title = "## Predefined Entity Types"
	relation_title = "## Predefined Relation Types"
	output_title = "## Output Format"

	try:
		entity_start = next(i for i, line in enumerate(lines) if entity_title in line)
	except StopIteration as exc:
		raise ValueError(f"Cannot find section: {entity_title}") from exc

	try:
		relation_start = next(i for i, line in enumerate(lines) if relation_title in line)
	except StopIteration as exc:
		raise ValueError(f"Cannot find section: {relation_title}") from exc

	try:
		output_start = next(i for i, line in enumerate(lines) if output_title in line)
	except StopIteration as exc:
		raise ValueError(f"Cannot find section: {output_title}") from exc

	entity_block = lines[entity_start:relation_start]
	relation_block = lines[relation_start:output_start]

	# Table rows are like: | `cell_type` | description |
	pattern = re.compile(r"^\|\s*`([^`]+)`\s*\|")

	entity_types = {
		m.group(1)
		for line in entity_block
		for m in [pattern.match(line)]
		if m is not None
	}
	relation_types = {
		m.group(1)
		for line in relation_block
		for m in [pattern.match(line)]
		if m is not None
	}

	if not entity_types:
		raise ValueError("No predefined entity types parsed from prompt")
	if not relation_types:
		raise ValueError("No predefined relation types parsed from prompt")

	return entity_types, relation_types


def unique_values(rows: list[dict[str, Any]], key: str) -> set[str]:
	vals: set[str] = set()
	for i, row in enumerate(rows, start=1):
		val = row.get(key)
		if val is None:
			continue
		if not isinstance(val, str):
			raise ValueError(f"Field '{key}' at record #{i} is not a string")
		vals.add(val.strip())
	return vals


def print_section(title: str, values: set[str]) -> None:
	print(f"\n{title.lower()} ({len(values)}):")
	for v in sorted(values):
		print(f"- {v}")


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Compare JSONL triple schema against predefined prompt schema"
	)
	parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL, help="Path to JSONL triples")
	parser.add_argument(
		"--prompt", type=Path, default=DEFAULT_PROMPT, help="Path to Triple_prompt.md"
	)
	parser.add_argument(
		"--save-report",
		type=Path,
		default=None,
		help="Optional path to save a JSON report",
	)
	args = parser.parse_args()

	rows = read_jsonl(args.jsonl)
	if not rows:
		raise ValueError(f"No records found in {args.jsonl}")

	head_types = unique_values(rows, "head_type")
	tail_types = unique_values(rows, "tail_type")
	relations = unique_values(rows, "relation")
	entity_types = head_types | tail_types

	predefined_entities, predefined_relations = parse_predefined_tables(args.prompt)

	entity_not_in_prompt = entity_types - predefined_entities
	entity_missing_in_data = predefined_entities - entity_types

	relation_not_in_prompt = relations - predefined_relations
	relation_missing_in_data = predefined_relations - relations

	print(f"jsonl: {args.jsonl}")
	print(f"prompt: {args.prompt}")
	print(f"records: {len(rows)}")

	print_section("HEAD_TYPES", head_types)
	print_section("TAIL_TYPES", tail_types)
	print_section("ENTITY_TYPES_UNION", entity_types)
	print_section("RELATIONS", relations)

	print_section("ENTITY_NOT_IN_PROMPT", entity_not_in_prompt)
	print_section("ENTITY_IN_PROMPT_BUT_MISSING_IN_DATA", entity_missing_in_data)
	print_section("RELATION_NOT_IN_PROMPT", relation_not_in_prompt)
	print_section("RELATION_IN_PROMPT_BUT_MISSING_IN_DATA", relation_missing_in_data)

	if args.save_report is not None:
		report = {
			"jsonl": str(args.jsonl),
			"prompt": str(args.prompt),
			"records": len(rows),
			"head_types": sorted(head_types),
			"tail_types": sorted(tail_types),
			"entity_types_union": sorted(entity_types),
			"relations": sorted(relations),
			"diff": {
				"entity_not_in_prompt": sorted(entity_not_in_prompt),
				"entity_in_prompt_but_missing_in_data": sorted(entity_missing_in_data),
				"relation_not_in_prompt": sorted(relation_not_in_prompt),
				"relation_in_prompt_but_missing_in_data": sorted(relation_missing_in_data),
			},
		}
		args.save_report.parent.mkdir(parents=True, exist_ok=True)
		args.save_report.write_text(
			json.dumps(report, ensure_ascii=False, indent=2),
			encoding="utf-8",
		)
		print(f"\nsaved report: {args.save_report}")


if __name__ == "__main__":
	main()
