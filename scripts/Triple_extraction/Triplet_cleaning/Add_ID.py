# English: Add global and per-PMID IDs to each triple in the JSONL dataset.
# 中文：为 JSONL 数据集中的每条三元组添加全局 ID 和同一 PMID 下的局部 ID。

import json
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
INPUT_FILE = PROJECT_ROOT / "data" / "Fine_tuning_dataset" / "triples_baichuan_m3_plus.jsonl"
OUTPUT_DIR = PROJECT_ROOT / "data" / "Fine_tuning_dataset" / "processed" / "Add_ID"
OUTPUT_FILE = OUTPUT_DIR / "triples_baichuan_m3_Add_ID.jsonl"


def add_ids(input_file: Path = INPUT_FILE, output_file: Path = OUTPUT_FILE) -> int:
    """Add ID1 and ID2 to each JSONL triple and return the number of written triples."""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    pmid_counts = defaultdict(int)
    total_count = 0

    with input_file.open("r", encoding="utf-8") as reader, output_file.open(
        "w", encoding="utf-8"
    ) as writer:
        for line_number, line in enumerate(reader, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                triple = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at line {line_number}: {exc}") from exc

            pmid = triple.get("PMID")
            if pmid is None:
                raise ValueError(f"Missing PMID at line {line_number}")

            total_count += 1
            pmid_counts[pmid] += 1

            triple.pop("ID1", None)
            triple.pop("ID2", None)
            triple_with_ids = {
                "ID1": str(total_count),
                "ID2": str(pmid_counts[pmid]),
                **triple,
            }

            writer.write(json.dumps(triple_with_ids, ensure_ascii=False) + "\n")

    return total_count


def main() -> None:
    written_count = add_ids()
    print(f"Added IDs to {written_count} triples.")
    print(f"Output file: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
