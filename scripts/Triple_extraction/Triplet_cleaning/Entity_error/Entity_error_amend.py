# English: Amend entity type labels in manual JSONL triples and merge them with entity-correct triples.
# Chinese: 修正人工 JSONL 三元组中的实体类型标签，并与实体正确的三元组文件合并。
import argparse
import json
from pathlib import Path
from typing import Any, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Entity_error"
)
DEFAULT_MANUAL_INPUT = DATA_DIR / "Entity_error_manual.jsonl"
DEFAULT_CORRECT_INPUT = (
    DATA_DIR / "triples_baichuan_m3_Add_ID_Format_correct_Error_entity_temp.jsonl"
)
DEFAULT_OUTPUT = (
    DATA_DIR / "triples_baichuan_m3_Add_ID_Format_correct_Entity_correct.jsonl"
)

TYPE_REPLACEMENTS = {
    "clinical_trial": "method",
    "phenology": "phenotype",
    "health_factor": "health_factors",
    "pathogen": "species",
    "physology": "physiology",
}
ENTITY_TYPE_KEYS = ("head_type", "tail_type")


def write_record(writer: TextIO, record: dict[str, Any]) -> None:
    """Write one JSON object as a JSONL record."""
    writer.write(json.dumps(record, ensure_ascii=False) + "\n")


def amend_entity_types(triple: dict[str, Any]) -> int:
    """
    Replace known wrong entity type labels in one triple.

    Returns:
        Number of fields amended in the triple.
    """
    amended_fields = 0

    for key in ENTITY_TYPE_KEYS:
        value = triple.get(key)
        if value in TYPE_REPLACEMENTS:
            triple[key] = TYPE_REPLACEMENTS[value]
            amended_fields += 1

    return amended_fields


def append_jsonl(
    input_file: Path,
    writer: TextIO,
    *,
    amend_types: bool = False,
) -> tuple[int, int, int]:
    """
    Append JSONL records to writer.

    Returns:
        A tuple of (written_records, amended_fields, invalid_records).
    """
    written_records = 0
    amended_fields = 0
    invalid_records = 0

    with input_file.open("r", encoding="utf-8") as reader:
        for line in reader:
            raw_line = line.strip()
            if not raw_line:
                continue

            try:
                triple = json.loads(raw_line)
            except json.JSONDecodeError:
                invalid_records += 1
                continue

            if not isinstance(triple, dict):
                invalid_records += 1
                continue

            if amend_types:
                amended_fields += amend_entity_types(triple)

            write_record(writer, triple)
            written_records += 1

    return written_records, amended_fields, invalid_records


def amend_and_merge(
    manual_input: Path = DEFAULT_MANUAL_INPUT,
    correct_input: Path = DEFAULT_CORRECT_INPUT,
    output_file: Path = DEFAULT_OUTPUT,
) -> tuple[int, int, int, int, int]:
    """
    Amend manual triples and merge them with triples that already passed entity checks.

    Returns:
        A tuple of (
            correct_records,
            manual_records,
            total_records,
            amended_fields,
            invalid_records,
        ).
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8") as writer:
        correct_records, _, correct_invalid = append_jsonl(correct_input, writer)
        manual_records, amended_fields, manual_invalid = append_jsonl(
            manual_input,
            writer,
            amend_types=True,
        )

    total_records = correct_records + manual_records
    invalid_records = correct_invalid + manual_invalid
    return (
        correct_records,
        manual_records,
        total_records,
        amended_fields,
        invalid_records,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Amend entity type labels in Entity_error_manual.jsonl and merge the "
            "records with triples_baichuan_m3_Add_ID_Format_correct_Error_entity_temp.jsonl."
        )
    )
    parser.add_argument(
        "--manual-input",
        type=Path,
        default=DEFAULT_MANUAL_INPUT,
        help="Manual JSONL file whose head_type and tail_type values should be amended.",
    )
    parser.add_argument(
        "--correct-input",
        type=Path,
        default=DEFAULT_CORRECT_INPUT,
        help="JSONL file containing triples that already passed entity checks.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Merged output JSONL file path.",
    )
    args = parser.parse_args()

    missing_files = [
        input_file
        for input_file in (args.manual_input, args.correct_input)
        if not input_file.exists()
    ]
    if missing_files:
        for input_file in missing_files:
            print(f"Input file does not exist: {input_file}")
        return

    (
        correct_records,
        manual_records,
        total_records,
        amended_fields,
        invalid_records,
    ) = amend_and_merge(args.manual_input, args.correct_input, args.output)

    print(f"Correct input file: {args.correct_input}")
    print(f"Manual input file: {args.manual_input}")
    print(f"Correct input records written: {correct_records}")
    print(f"Manual input records written: {manual_records}")
    print(f"Entity type fields amended: {amended_fields}")
    print(f"Invalid records skipped: {invalid_records}")
    print(f"Total output records: {total_records}")
    print(f"Output file: {args.output}")


if __name__ == "__main__":
    main()
