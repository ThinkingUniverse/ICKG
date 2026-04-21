# English: Judge whether the format-correct JSONL triple file still contains malformed records.
# Chinese: 判断格式正确 JSONL 三元组文件中是否仍存在格式错误记录，仅打印统计信息。
import json
from collections.abc import Sized
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Format_error"
    / "triples_baichuan_m3_Add_ID_Format_correct.jsonl"
)

REQUIRED_KEYS = (
    "ID1",
    "ID2",
    "PMID",
    "head",
    "head_type",
    "relation",
    "tail",
    "tail_type",
    "source_sentence",
    "score",
)


def is_empty_value(value: Any) -> bool:
    """Return True when a required field value should be treated as empty."""
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, Sized) and not isinstance(value, (str, bytes, bytearray)):
        return len(value) == 0

    return False


def find_format_errors(triple: dict[str, Any]) -> list[str]:
    """Return all format errors for one triple."""
    reasons: list[str] = []

    for key in REQUIRED_KEYS:
        if key not in triple:
            reasons.append(f"Missing {key} key")
            reasons.append(f"Missing {key} value")
        elif is_empty_value(triple[key]):
            reasons.append(f"Missing {key} value")

    return reasons


def judge_format(
    input_file: Path = INPUT_FILE, max_examples: int = 10
) -> tuple[int, int, int]:
    """
    Check whether input_file contains malformed triples and print examples.

    Returns:
        A tuple of (total_lines, valid_triples, invalid_triples).
    """
    total_lines = 0
    valid_triples = 0
    invalid_triples = 0
    examples: list[dict[str, Any]] = []

    with input_file.open("r", encoding="utf-8") as reader:
        for line_number, line in enumerate(reader, start=1):
            total_lines += 1
            raw_line = line.strip()

            if not raw_line:
                invalid_triples += 1
                if len(examples) < max_examples:
                    examples.append(
                        {
                            "line_number": line_number,
                            "reason": "Missing line value",
                            "raw_line": raw_line,
                        }
                    )
                continue

            try:
                triple = json.loads(raw_line)
            except json.JSONDecodeError:
                invalid_triples += 1
                if len(examples) < max_examples:
                    examples.append(
                        {
                            "line_number": line_number,
                            "reason": "Invalid JSON",
                            "raw_line": raw_line,
                        }
                    )
                continue

            if not isinstance(triple, dict):
                invalid_triples += 1
                if len(examples) < max_examples:
                    examples.append(
                        {
                            "line_number": line_number,
                            "reason": "JSON value is not an object",
                            "raw_line": raw_line,
                        }
                    )
                continue

            reasons = find_format_errors(triple)
            if reasons:
                invalid_triples += 1
                if len(examples) < max_examples:
                    examples.append(
                        {
                            "line_number": line_number,
                            "reason": "; ".join(reasons),
                            **triple,
                        }
                    )
            else:
                valid_triples += 1

    print(f"Input file: {input_file}")
    print(f"Total lines: {total_lines}")
    print(f"Valid triples: {valid_triples}")
    print(f"Invalid triples: {invalid_triples}")

    if invalid_triples == 0:
        print("Result: No malformed triples found.")
    else:
        print("Result: Malformed triples found.")
        print(f"Showing first {len(examples)} malformed examples:")
        for example in examples:
            print(json.dumps(example, ensure_ascii=False))

    return total_lines, valid_triples, invalid_triples


def main() -> None:
    judge_format()


if __name__ == "__main__":
    main()
