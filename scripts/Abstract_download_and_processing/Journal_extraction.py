from __future__ import annotations

import argparse
import json
from pathlib import Path

from openpyxl import Workbook


def extract_journal_counts(records: list[dict]) -> list[tuple[str, int]]:
	journal_counts: dict[str, int] = {}

	for item in records:
		if not isinstance(item, dict):
			continue

		journal = str(item.get("Journal", "")).strip()
		if not journal:
			continue

		journal_counts[journal] = journal_counts.get(journal, 0) + 1

	return list(journal_counts.items())


def main() -> None:
	project_root = Path(__file__).resolve().parents[2]
	default_input = (
		project_root
		/ "data"
		/ "pubmed_output"
		/ "merge"
		/ "PubMed_abstract_2016_01_01_2026_03_31.json"
	)
	default_output = project_root / "data" / "pubmed_output" / "merge" / "Journal_unique.xlsx"

	parser = argparse.ArgumentParser(
		description="Extract Journal values with occurrence counts from PubMed merged JSON and write an XLSX file."
	)
	parser.add_argument("-i", "--input", type=Path, default=default_input, help="Input JSON file path")
	parser.add_argument("-o", "--output", type=Path, default=default_output, help="Output XLSX file path")
	args = parser.parse_args()

	with args.input.open("r", encoding="utf-8") as f:
		data = json.load(f)

	if not isinstance(data, list):
		raise ValueError("Input JSON must be a list of objects.")

	journal_counts = extract_journal_counts(data)
	journal_counts.sort(key=lambda x: (-x[1], x[0]))

	args.output.parent.mkdir(parents=True, exist_ok=True)
	workbook = Workbook()
	worksheet = workbook.active
	worksheet.title = "Journals"
	worksheet.append(["Journal", "Count"])
	for journal, count in journal_counts:
		worksheet.append([journal, count])
	workbook.save(args.output)

	print(f"Done. Unique journals: {len(journal_counts)}")
	print(f"XLSX saved to: {args.output}")


if __name__ == "__main__":
	main()
