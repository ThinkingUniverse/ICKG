# English: Split JSONL triples by low-frequency entity types.
# Chinese: Count entity type frequency and write low-frequency entity triples separately.
import argparse
import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Format_error"
    / "triples_baichuan_m3_Add_ID_Format_correct.jsonl"
)
DEFAULT_ERROR_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Entity_error"
    / "Entity_error.jsonl"
)
DEFAULT_CORRECT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Entity_error"
    / "triples_baichuan_m3_Add_ID_Format_correct_Error_entity_temp.jsonl"
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


def split_by_error_entity(
    jsonl_path: Path,
    error_output_path: Path,
    correct_output_path: Path,
    low_frequency_types: set[str],
) -> tuple[int, int, int]:
    """Write low-frequency entity triples and triples without low-frequency types."""
    error_lines = 0
    correct_lines = 0
    invalid_lines = 0

    error_output_path.parent.mkdir(parents=True, exist_ok=True)
    correct_output_path.parent.mkdir(parents=True, exist_ok=True)

    with jsonl_path.open("r", encoding="utf-8") as src, error_output_path.open(
        "w", encoding="utf-8"
    ) as error_dst, correct_output_path.open("w", encoding="utf-8") as correct_dst:
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
            head_is_low_frequency = (
                isinstance(head_type, str) and head_type.strip() in low_frequency_types
            )
            tail_is_low_frequency = (
                isinstance(tail_type, str) and tail_type.strip() in low_frequency_types
            )

            if head_is_low_frequency or tail_is_low_frequency:
                error_dst.write(raw_line + "\n")
                error_lines += 1
            else:
                correct_dst.write(raw_line + "\n")
                correct_lines += 1

    return error_lines, correct_lines, invalid_lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Split triples whose head_type or tail_type frequency is below the "
            "threshold from triples without low-frequency entity types."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Input JSONL file path.",
    )
    parser.add_argument(
        "--error-output",
        type=Path,
        default=DEFAULT_ERROR_OUTPUT,
        help="Output JSONL path for triples containing low-frequency entity types.",
    )
    parser.add_argument(
        "--correct-output",
        type=Path,
        default=DEFAULT_CORRECT_OUTPUT,
        help="Output JSONL path for triples without low-frequency entity types.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=1000,
        help="Low-frequency threshold. Types with frequency below this value are selected.",
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

    error_lines, correct_lines, split_invalid_lines = split_by_error_entity(
        args.input,
        args.error_output,
        args.correct_output,
        low_frequency_types,
    )

    print(f"Input file: {args.input}")
    print(f"Valid records: {valid_lines}")
    print(f"Invalid records while counting: {invalid_lines}")
    print(f"Unique entity types: {len(type_counter)}")
    print("\nAll entity type frequencies, sorted descending:")
    for entity_type, count in type_counter.most_common():
        print(f"{entity_type} {count}")

    print(f"Threshold: {args.threshold}")
    print(f"Low-frequency type count: {len(low_frequency_types)}")
    print("Selected low-frequency types, sorted ascending:")
    for entity_type, count in sorted(
        ((t, type_counter[t]) for t in low_frequency_types), key=lambda x: (x[1], x[0])
    ):
        print(f"{entity_type} {count}")
    print(f"Invalid records while splitting: {split_invalid_lines}")
    print(f"Low-frequency entity triples: {error_lines}")
    print(f"Triples without low-frequency entity types: {correct_lines}")
    print(f"Error output file: {args.error_output}")
    print(f"Correct output file: {args.correct_output}")


if __name__ == "__main__":
    main()
