# English: Verify that every relation in a JSONL triples file is included in the
# English: predefined relation types table defined in Triple_prompt_v2.md; emit a
# English: count CSV only when the check fully passes.
# Chinese: 校验 JSONL 三元组文件中出现的所有 relation 是否都在 Triple_prompt_v2.md
# Chinese: 预定义关系类型表中；仅当全部命中时输出按 count 降序的 CSV。
import argparse
import csv
import json
import re
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
    / "Relation_error"
    / "Second_batch"
    / "triples_baichuan_m3_Add_ID_Format_Entity_Relation_Correct.jsonl"
)
DEFAULT_PROMPT = PROJECT_ROOT / "prompts" / "Triple_prompt_v2.md"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Relation_error"
    / "Second_batch"
    / "Relationship_instance_statistics_predefined.csv"
)


def load_predefined_relations(prompt_path: Path) -> set[str]:
    """从 Triple_prompt_v2.md 的关系表节点解析反引号包裹的关系名集合。"""
    relations: set[str] = set()
    in_relation_section = False
    relation_pattern = re.compile(r"^\|\s*`([^`]+)`\s*\|")

    with prompt_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped_line = line.strip()
            if stripped_line == "## Predefined Relation Types Table":
                in_relation_section = True
                continue

            # 遇到下一个二级标题即退出关系表节点
            if in_relation_section and stripped_line.startswith("## "):
                break

            if not in_relation_section:
                continue

            match = relation_pattern.match(stripped_line)
            if match:
                relations.add(match.group(1).strip())

    return relations


def count_relations(jsonl_path: Path) -> tuple[Counter, int, int]:
    """逐行解析 JSONL，统计 relation 字段的频次；返回 (计数器, 有效行数, 非法行数)。"""
    relation_counter: Counter = Counter()
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

            relation = obj.get("relation")
            if isinstance(relation, str) and relation.strip():
                relation_counter[relation.strip()] += 1

    return relation_counter, valid_lines, invalid_lines


def write_relation_csv(output_path: Path, relation_counter: Counter) -> None:
    """以 (relation, count) 两列、count 降序写出 CSV。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["relation", "count"])
        for relation, count in relation_counter.most_common():
            writer.writerow([relation, count])


def main() -> None:
    parser = argparse.ArgumentParser(
        add_help=False,
        description=(
            "校验 JSONL 三元组文件中的 relation 是否全部命中 Triple_prompt_v2.md "
            "预定义关系类型表；全部命中则输出按 count 降序的 CSV，否则仅在控制台"
            "列出未命中关系及其频次，不输出 CSV。"
        ),
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="显示此帮助信息并退出。",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=DEFAULT_INPUT,
        help="待校验的 JSONL 文件路径（每行包含 relation 字段）。",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=Path,
        default=DEFAULT_PROMPT,
        help="包含预定义关系类型表的 Triple_prompt_v2.md 路径。",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="校验通过时写出的 CSV 路径（列：relation、count，count 降序）。",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"输入文件不存在: {args.input}")
        return

    if not args.prompt.exists():
        print(f"Prompt 文件不存在: {args.prompt}")
        return

    predefined_relations = load_predefined_relations(args.prompt)
    if not predefined_relations:
        print(f"未在 prompt 中解析到任何预定义关系: {args.prompt}")
        return

    relation_counter, valid_lines, invalid_lines = count_relations(args.input)

    print(f"输入文件: {args.input}")
    print(f"Prompt 文件: {args.prompt}")
    print(f"有效记录: {valid_lines}")
    print(f"非法记录: {invalid_lines}")
    print(f"出现的唯一 relation 数: {len(relation_counter)}")
    print(f"预定义关系数: {len(predefined_relations)}")

    undefined_relations = set(relation_counter) - predefined_relations

    if not undefined_relations:
        print("校验通过：全部 relation 均在预定义关系类型表中。")
        write_relation_csv(args.output, relation_counter)
        print(f"已输出统计 CSV: {args.output}")
        return

    print(f"校验未通过：存在 {len(undefined_relations)} 个未在预定义表中的 relation。")
    print("未命中关系（按 count 降序）:")
    # 按 count 降序、count 相同则按关系名升序输出
    for relation, count in sorted(
        ((r, relation_counter[r]) for r in undefined_relations),
        key=lambda x: (-x[1], x[0]),
    ):
        print(f"{relation}\t{count}")
    print("校验未通过，不会生成 CSV。")


if __name__ == "__main__":
    main()
