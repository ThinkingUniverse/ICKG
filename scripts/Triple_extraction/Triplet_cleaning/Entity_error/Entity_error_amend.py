# English: Amend entity type labels in manual JSONL triples and merge them with entity-correct triples.
# Chinese: 修正人工 JSONL 三元组中的实体类型标签，并与实体正确的三元组文件合并。
import argparse
import json
from pathlib import Path
from typing import Any, Optional, TextIO


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
DEFAULT_TYPE_REPLACEMENTS_FILE = DATA_DIR / "entity_type_replacements.txt"
ENTITY_TYPE_KEYS = ("head_type", "tail_type")


def normalize_mapping_value(value: str) -> str:
    """Normalize one mapping value read from a tab-separated text file."""
    normalized = value.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {'"', "'"}:
        normalized = normalized[1:-1].strip()
    return normalized


def load_type_replacements(mapping_file: Path) -> dict[str, str]:
    """Load entity type replacements from a tab-separated text file."""
    replacements: dict[str, str] = {}

    with mapping_file.open("r", encoding="utf-8") as reader:
        for line_number, line in enumerate(reader, start=1):
            raw_line = line.strip()
            if not raw_line:
                continue

            parts = raw_line.split("\t")
            if len(parts) != 2:
                raise ValueError(
                    f"映射文件第 {line_number} 行格式无效，应为两列并使用制表符分隔: {mapping_file}"
                )

            source = normalize_mapping_value(parts[0])
            target = normalize_mapping_value(parts[1])
            if not source or not target:
                raise ValueError(
                    f"映射文件第 {line_number} 行包含空值: {mapping_file}"
                )

            replacements[source] = target

    return replacements


def write_record(writer: TextIO, record: dict[str, Any]) -> None:
    """Write one JSON object as a JSONL record."""
    writer.write(json.dumps(record, ensure_ascii=False) + "\n")


def amend_entity_types(triple: dict[str, Any], type_replacements: dict[str, str]) -> int:
    """
    Replace known wrong entity type labels in one triple.

    Returns:
        Number of fields amended in the triple.
    """
    amended_fields = 0

    for key in ENTITY_TYPE_KEYS:
        value = triple.get(key)
        if value in type_replacements:
            triple[key] = type_replacements[value]
            amended_fields += 1

    return amended_fields


def append_jsonl(
    input_file: Path,
    writer: TextIO,
    *,
    type_replacements: Optional[dict[str, str]] = None,
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
                amended_fields += amend_entity_types(triple, type_replacements or {})

            write_record(writer, triple)
            written_records += 1

    return written_records, amended_fields, invalid_records


def amend_and_merge(
    manual_input: Path = DEFAULT_MANUAL_INPUT,
    correct_input: Path = DEFAULT_CORRECT_INPUT,
    output_file: Path = DEFAULT_OUTPUT,
    type_replacements: Optional[dict[str, str]] = None,
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
            type_replacements=type_replacements,
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
        add_help=False,
        description=(
            "修正 Entity_error_manual.jsonl 中的实体类型标签，并与已经通过实体检查的 "
            "JSONL 三元组文件合并。"
        )
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        default=argparse.SUPPRESS,
        help="显示帮助信息并退出。",
    )
    parser.add_argument(
        "--manual-input",
        type=Path,
        default=DEFAULT_MANUAL_INPUT,
        help="需要修正 head_type 和 tail_type 的人工标注 JSONL 文件。",
    )
    parser.add_argument(
        "--correct-input",
        type=Path,
        default=DEFAULT_CORRECT_INPUT,
        help="已经通过实体检查的 JSONL 三元组文件。",
    )
    parser.add_argument(
        "--type-replacements",
        type=Path,
        default=DEFAULT_TYPE_REPLACEMENTS_FILE,
        help=(
            "实体类型替换映射文件，需使用制表符分隔两列，例如 \"health_factor\"\t\"health_factors\"。"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="合并后的输出 JSONL 文件路径。",
    )
    args = parser.parse_args()

    missing_files = [
        input_file
        for input_file in (args.manual_input, args.correct_input, args.type_replacements)
        if not input_file.exists()
    ]
    if missing_files:
        for input_file in missing_files:
            print(f"输入文件不存在: {input_file}")
        return

    try:
        type_replacements = load_type_replacements(args.type_replacements)
    except ValueError as error:
        print(error)
        return

    (
        correct_records,
        manual_records,
        total_records,
        amended_fields,
        invalid_records,
    ) = amend_and_merge(
        args.manual_input,
        args.correct_input,
        args.output,
        type_replacements=type_replacements,
    )

    print(f"正确输入文件: {args.correct_input}")
    print(f"人工输入文件: {args.manual_input}")
    print(f"类型替换映射文件: {args.type_replacements}")
    print(f"正确输入写入记录数: {correct_records}")
    print(f"人工输入写入记录数: {manual_records}")
    print(f"实体类型字段修正数: {amended_fields}")
    print(f"跳过的无效记录数: {invalid_records}")
    print(f"输出总记录数: {total_records}")
    print(f"输出文件: {args.output}")


if __name__ == "__main__":
    main()
