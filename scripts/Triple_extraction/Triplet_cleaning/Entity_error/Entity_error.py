# English: Identify low-frequency entity types in a JSONL triples file and split records into error/correct outputs via command-line arguments.
# Chinese: 通过命令行参数读取 JSONL 三元组文件，识别低频实体类型，并将记录拆分为错误输出和正确输出。
import argparse
import json
from collections import Counter
from pathlib import Path


def count_entity_types(jsonl_path: Path) -> tuple[Counter[str], int, int]:
    """统计 JSONL 文件中 head_type 和 tail_type 的合并频次。"""
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
    """将低频实体三元组与非低频实体三元组分别写入不同文件。"""
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
        description="按实体类型频次拆分三元组，筛出包含低频 head_type 或 tail_type 的记录。",
        epilog=(
            "示例:\n"
            "  python Entity_error.py "
            "--input data/Fine_tuning_dataset/processed/Format_error/input.jsonl "
            "--error-output data/Fine_tuning_dataset/processed/Entity_error/error.jsonl "
            "--correct-output data/Fine_tuning_dataset/processed/Entity_error/correct.jsonl "
            "--threshold 1000"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False,
    )
    parser._positionals.title = "位置参数"
    parser._optionals.title = "可选参数"
    parser.add_argument("-h", "--help", action="help", help="显示此帮助信息并退出。")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="输入 JSONL 文件路径。",
    )
    parser.add_argument(
        "--error-output",
        type=Path,
        required=True,
        help="包含低频实体类型的错误记录输出路径。",
    )
    parser.add_argument(
        "--correct-output",
        type=Path,
        required=True,
        help="不包含低频实体类型的正确记录输出路径。",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=1000,
        help="低频阈值，小于该值的实体类型会被判定为低频。默认值：1000。",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"输入文件不存在: {args.input}")
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

    print(f"输入文件: {args.input}")
    print(f"有效记录数: {valid_lines}")
    print(f"统计阶段无效记录数: {invalid_lines}")
    print(f"实体类型总数: {len(type_counter)}")
    print("\n全部实体类型频次（按降序排序）:")
    for entity_type, count in type_counter.most_common():
        print(f"{entity_type} {count}")

    print(f"阈值: {args.threshold}")
    print(f"低频实体类型数量: {len(low_frequency_types)}")
    print("筛选出的低频实体类型（按升序排序）:")
    for entity_type, count in sorted(
        ((t, type_counter[t]) for t in low_frequency_types), key=lambda x: (x[1], x[0])
    ):
        print(f"{entity_type} {count}")
    print(f"拆分阶段无效记录数: {split_invalid_lines}")
    print(f"低频实体三元组数量: {error_lines}")
    print(f"非低频实体三元组数量: {correct_lines}")
    print(f"错误输出文件: {args.error_output}")
    print(f"正确输出文件: {args.correct_output}")


if __name__ == "__main__":
    main()
