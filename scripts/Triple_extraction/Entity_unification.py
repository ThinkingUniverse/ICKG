import argparse
import json
from collections import Counter
from pathlib import Path


DEFAULT_INPUT = Path(
	r"C:\Users\Administrator\Desktop\ICKG\data\Fine_tuning_dataset\triples_baichuan_m3_plus.jsonl"
)
DEFAULT_OUTPUT = Path(
	r"C:\Users\Administrator\Desktop\ICKG\data\Fine_tuning_dataset\Error_entity\Error_entity.jsonl"
)


def count_entity_types(jsonl_path: Path) -> tuple[Counter[str], int, int]:
	"""Count merged frequencies of head_type and tail_type from a JSONL file."""
	type_counter: Counter[str] = Counter()
	valid_lines = 0
	invalid_lines = 0

	with jsonl_path.open("r", encoding="utf-8") as f:
		for line in f:
			line = line.strip()
			if not line:
				continue

			try:
				obj = json.loads(line)
			except json.JSONDecodeError:
				invalid_lines += 1
				continue

			if not isinstance(obj, dict):
				invalid_lines += 1
				continue

			valid_lines += 1

			head_type = obj.get("head_type")
			if isinstance(head_type, str) and head_type.strip():
				type_counter[head_type.strip()] += 1

			tail_type = obj.get("tail_type")
			if isinstance(tail_type, str) and tail_type.strip():
				type_counter[tail_type.strip()] += 1

	return type_counter, valid_lines, invalid_lines


def extract_error_entity_triples(
	jsonl_path: Path, output_path: Path, selected_types: set[str]
) -> tuple[int, int]:
	"""Write triples whose head_type or tail_type is in selected_types."""
	matched_lines = 0
	invalid_lines = 0

	output_path.parent.mkdir(parents=True, exist_ok=True)

	with jsonl_path.open("r", encoding="utf-8") as src, output_path.open(
		"w", encoding="utf-8"
	) as dst:
		for line in src:
			raw_line = line.strip()
			if not raw_line:
				continue

			try:
				obj = json.loads(raw_line)
			except json.JSONDecodeError:
				invalid_lines += 1
				continue

			if not isinstance(obj, dict):
				invalid_lines += 1
				continue

			head_type = obj.get("head_type")
			tail_type = obj.get("tail_type")
			head_in = isinstance(head_type, str) and head_type.strip() in selected_types
			tail_in = isinstance(tail_type, str) and tail_type.strip() in selected_types

			if head_in or tail_in:
				dst.write(raw_line + "\n")
				matched_lines += 1

	return matched_lines, invalid_lines


def main() -> None:
	parser = argparse.ArgumentParser(
		description=(
			"提取 head_type 或 tail_type 频次小于阈值的三元组，输出到 Error_entity.jsonl"
		)
	)
	parser.add_argument(
		"--input",
		type=Path,
		default=DEFAULT_INPUT,
		help="输入 JSONL 文件路径（默认 triples_baichuan_m3_plus.jsonl）",
	)
	parser.add_argument(
		"--output",
		type=Path,
		default=DEFAULT_OUTPUT,
		help="输出 JSONL 文件路径（默认 Error_entity/Error_entity.jsonl）",
	)
	parser.add_argument(
		"--threshold",
		type=int,
		default=1000,
		help="筛选阈值：仅保留频次小于该值的类型（默认 1000）",
	)
	args = parser.parse_args()

	if not args.input.exists():
		print(f"文件不存在: {args.input}")
		return

	type_counter, valid_lines, invalid_lines = count_entity_types(args.input)
	selected_types = {entity_type for entity_type, count in type_counter.items() if count < args.threshold}

	matched_lines, extract_invalid_lines = extract_error_entity_triples(
		args.input, args.output, selected_types
	)

	print(f"输入文件: {args.input}")
	print(f"有效记录数: {valid_lines}")
	print(f"无效记录数: {invalid_lines}")
	print(f"类型唯一值个数: {len(type_counter)}")
	print("\n所有类型频次（按频次降序）:")
	for entity_type, count in type_counter.most_common():
		print(f"{entity_type} {count}")

	print(f"阈值: {args.threshold}")
	print(f"低频类型个数: {len(selected_types)}")
	print("选择的低频类型（按频次升序）:")
	for entity_type, count in sorted(
		((t, type_counter[t]) for t in selected_types), key=lambda x: (x[1], x[0])
	):
		print(f"{entity_type} {count}")
	print(f"提取阶段无效记录数: {extract_invalid_lines}")
	print(f"命中三元组数: {matched_lines}")
	print(f"输出文件: {args.output}")


if __name__ == "__main__":
	main()
