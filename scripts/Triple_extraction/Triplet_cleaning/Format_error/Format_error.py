# English: Split JSONL triples into malformed records with reasons and format-correct records.
# Chinese: Check JSONL triple format and write malformed records and correct records separately.
import json
from collections.abc import Sized
from pathlib import Path
from typing import Any, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[4]
INPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Add_ID"
    / "triples_baichuan_m3_Add_ID.jsonl"
)
ERROR_OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Format_error"
    / "Format_error.jsonl"
)
CORRECT_OUTPUT_FILE = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Format_error"
    / "triples_baichuan_m3_Add_ID_Format_correct_temp.jsonl"
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


def write_record(writer: TextIO, record: dict[str, Any]) -> None:
    """Write one JSON object as a JSONL record."""
    writer.write(json.dumps(record, ensure_ascii=False) + "\n")


def split_by_format(
    input_file: Path = INPUT_FILE,
    error_output_file: Path = ERROR_OUTPUT_FILE,
    correct_output_file: Path = CORRECT_OUTPUT_FILE,
) -> tuple[int, int, int]:
    """
    Write invalid triples to error_output_file and valid triples to correct_output_file.

    Returns:
        A tuple of (total_lines, valid_triples, invalid_triples).
    """
    error_output_file.parent.mkdir(parents=True, exist_ok=True)
    correct_output_file.parent.mkdir(parents=True, exist_ok=True)

    total_lines = 0
    valid_triples = 0
    invalid_triples = 0

    with input_file.open("r", encoding="utf-8") as reader, error_output_file.open(
        "w", encoding="utf-8"
    ) as error_writer, correct_output_file.open(
        "w", encoding="utf-8"
    ) as correct_writer:
        for line_number, line in enumerate(reader, start=1):
            total_lines += 1
            raw_line = line.strip()

            if not raw_line:
                invalid_triples += 1
                write_record(
                    error_writer,
                    {
                        "reason": "Missing line value",
                        "line_number": line_number,
                        "raw_line": raw_line,
                    },
                )
                continue

            try:
                triple = json.loads(raw_line)
            except json.JSONDecodeError:
                invalid_triples += 1
                write_record(
                    error_writer,
                    {
                        "reason": "Invalid JSON",
                        "line_number": line_number,
                        "raw_line": raw_line,
                    },
                )
                continue

            if not isinstance(triple, dict):
                invalid_triples += 1
                write_record(
                    error_writer,
                    {
                        "reason": "JSON value is not an object",
                        "line_number": line_number,
                        "raw_line": raw_line,
                    },
                )
                continue

            reasons = find_format_errors(triple)
            if reasons:
                invalid_triples += 1
                write_record(error_writer, {"reason": "; ".join(reasons), **triple})
            else:
                valid_triples += 1
                write_record(correct_writer, triple)

    return total_lines, valid_triples, invalid_triples


def main() -> None:
    total_lines, valid_triples, invalid_triples = split_by_format()

    print(f"Total lines: {total_lines}")
    print(f"Valid triples: {valid_triples}")
    print(f"Invalid triples: {invalid_triples}")
    print(f"Error output file: {ERROR_OUTPUT_FILE}")
    print(f"Correct output file: {CORRECT_OUTPUT_FILE}")


if __name__ == "__main__":
    main()
