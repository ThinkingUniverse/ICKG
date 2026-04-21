"""
功能: 从 triples_baichuan_m3_plus.jsonl 中提取每条记录的 PMID，按首次出现顺序去重，并输出到 processed_pmids_1.txt。
Function: Extract PMIDs from triples_baichuan_m3_plus.jsonl, deduplicate them in first-seen order, and write them to processed_pmids_1.txt.
"""

import json
from pathlib import Path


def extract_unique_pmids(input_path: Path, output_path: Path) -> tuple[int, int]:
	seen = set()
	unique_pmids = []
	total_lines = 0

	with input_path.open("r", encoding="utf-8") as infile:
		for line in infile:
			line = line.strip()
			if not line:
				continue

			total_lines += 1
			try:
				obj = json.loads(line)
			except json.JSONDecodeError:
				continue

			pmid = str(obj.get("PMID", "")).strip()
			if not pmid or pmid in seen:
				continue

			seen.add(pmid)
			unique_pmids.append(pmid)

	output_path.parent.mkdir(parents=True, exist_ok=True)
	with output_path.open("w", encoding="utf-8") as outfile:
		for pmid in unique_pmids:
			outfile.write(f"{pmid}\n")

	return total_lines, len(unique_pmids)


def main() -> None:
	project_root = Path(__file__).resolve().parents[2]
	input_file = project_root / "data" / "Fine_tuning_dataset" / "triples_baichuan_m3_plus.jsonl"
	output_file = project_root / "data" / "Fine_tuning_dataset" / "processed_pmids_1.txt"

	if not input_file.exists():
		raise FileNotFoundError(f"Input file not found: {input_file}")

	total, unique = extract_unique_pmids(input_file, output_file)
	print(f"Processed lines: {total}")
	print(f"Unique PMIDs: {unique}")
	print(f"Output file: {output_file}")


if __name__ == "__main__":
	main()
