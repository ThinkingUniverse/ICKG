# English: Judge whether the format-correct JSONL triple file still contains malformed records.
# Chinese: 判断格式正确 JSONL 三元组文件中是否仍存在格式错误记录，仅打印统计信息。
import argparse
import json
from collections.abc import Sized
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INPUT_FILE = (
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


def build_report(
    input_file: Path,
    total_lines: int,
    valid_triples: int,
    invalid_triples: int,
    examples: list[dict[str, Any]],
) -> str:
    """构建格式检查结果报告文本。"""
    report_lines = [
        f"Input file: {input_file}",
        f"Total lines: {total_lines}",
        f"Valid triples: {valid_triples}",
        f"Invalid triples: {invalid_triples}",
    ]

    if invalid_triples == 0:
        report_lines.append("Result: No malformed triples found.")
    else:
        report_lines.append("Result: Malformed triples found.")
        report_lines.append(f"Showing first {len(examples)} malformed examples:")
        report_lines.extend(
            json.dumps(example, ensure_ascii=False) for example in examples
        )

    return "\n".join(report_lines)


def judge_format(
    input_file: Path = DEFAULT_INPUT_FILE,
    output_file: Optional[Path] = None,
    max_examples: int = 10,
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

    report = build_report(
        input_file=input_file,
        total_lines=total_lines,
        valid_triples=valid_triples,
        invalid_triples=invalid_triples,
        examples=examples,
    )

    if output_file is None:
        print(report)
    else:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(report + "\n", encoding="utf-8")
        print(f"Output file: {output_file}")

    return total_lines, valid_triples, invalid_triples


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="检查 JSONL 三元组文件中是否仍有格式错误，并输出统计结果。"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_FILE,
        help=f"输入 JSONL 文件路径，默认：{DEFAULT_INPUT_FILE}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="统计结果输出文件路径；默认打印到标准输出。",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=10,
        help="最多输出多少条格式错误示例，默认：10",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    judge_format(
        input_file=args.input,
        output_file=args.output,
        max_examples=args.max_examples,
    )


if __name__ == "__main__":
    main()
