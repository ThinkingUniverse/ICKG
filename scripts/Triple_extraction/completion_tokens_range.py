import argparse
import json
from pathlib import Path
from statistics import median


def analyze_completion_tokens(jsonl_path: Path) -> None:
	if not jsonl_path.exists():
		print(f"文件不存在: {jsonl_path}")
		return

	min_tokens = None
	max_tokens = None
	max_pmid = None
	valid_count = 0
	invalid_count = 0
	tokens_list = []

	with jsonl_path.open("r", encoding="utf-8") as f:
		for line_no, line in enumerate(f, start=1):
			line = line.strip()
			if not line:
				continue

			try:
				obj = json.loads(line)
				tokens = int(obj["completion_tokens"])
				pmid = str(obj.get("PMID", ""))
			except (json.JSONDecodeError, KeyError, TypeError, ValueError):
				invalid_count += 1
				continue

			valid_count += 1
			tokens_list.append(tokens)
			if min_tokens is None or tokens < min_tokens:
				min_tokens = tokens
			if max_tokens is None or tokens > max_tokens:
				max_tokens = tokens
				max_pmid = pmid

	print(f"输入文件: {jsonl_path}")
	print(f"有效三元组数: {valid_count}")
	print(f"无效行数: {invalid_count}")

	if valid_count == 0:
		print("未找到可用的 completion_tokens 数据。")
		return

	mean_tokens = sum(tokens_list) / valid_count
	median_tokens = median(tokens_list)

	print(f"completion_tokens 范围: {min_tokens} ~ {max_tokens}")
	print(f"completion_tokens 中位数: {median_tokens}")
	print(f"completion_tokens 均值: {mean_tokens:.2f}")
	print(f"completion_tokens 最大值对应 PMID: {max_pmid}")


def main() -> None:
	default_path = Path(
		r"C:\Users\Administrator\Desktop\ICKG\data\Fine_tuning_dataset\triples_usage.jsonl"
	)

	parser = argparse.ArgumentParser(
		description="统计 JSONL 文件中 completion_tokens 的最小值和最大值范围"
	)
	parser.add_argument(
		"--input",
		type=Path,
		default=default_path,
		help="JSONL 文件路径（默认使用 triples_usage.jsonl）",
	)
	args = parser.parse_args()

	analyze_completion_tokens(args.input)


if __name__ == "__main__":
	main()
