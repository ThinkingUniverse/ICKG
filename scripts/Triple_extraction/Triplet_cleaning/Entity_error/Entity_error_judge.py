# English: Count head_type and tail_type frequencies and report low-frequency entity types.
# Chinese: 统计 head_type 和 tail_type 的频次，并打印低频实体类型信息。
import argparse
import json
import sys
from collections import Counter
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Entity_error"
    / "triples_baichuan_m3_Add_ID_Format_correct_Entity_correct.jsonl"
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

            for field_name in ("head_type", "tail_type"):
                entity_type = obj.get(field_name)
                if isinstance(entity_type, str) and entity_type.strip():
                    type_counter[entity_type.strip()] += 1

    return type_counter, valid_lines, invalid_lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Count head_type/tail_type frequencies and print entity types whose "
            "frequency is below the threshold."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Input JSONL file path.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=1000,
        help="Low-frequency threshold. Types with frequency below this value are reported.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input file does not exist: {args.input}")
        return

    type_counter, valid_lines, invalid_lines = count_entity_types(args.input)
    low_frequency_types = {
        entity_type
        for entity_type, count in type_counter.items()
        if count < args.threshold
    }

    print(f"Input file: {args.input}")
    print(f"Valid records: {valid_lines}")
    print(f"Invalid records while counting: {invalid_lines}")
    print(f"Unique entity types: {len(type_counter)}")
    print("\nAll head_type/tail_type frequencies, sorted descending:")
    for entity_type, count in type_counter.most_common():
        print(f"{entity_type} {count}")

    print(f"\nThreshold: {args.threshold}")
    print(f"Has entity types below threshold: {'Yes' if low_frequency_types else 'No'}")
    print(f"Low-frequency entity type count: {len(low_frequency_types)}")
    if low_frequency_types:
        print("Entity types below threshold, sorted ascending:")
        for entity_type, count in sorted(
            ((t, type_counter[t]) for t in low_frequency_types),
            key=lambda x: (x[1], x[0]),
        ):
            print(f"{entity_type} {count}")


if __name__ == "__main__":
    main()
