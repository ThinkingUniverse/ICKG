# Process relation-error triples and merge them into the relation-correct dataset.
# 处理 relation 不在预定义类型中的三元组，并将清洗结果合并到关系正确的数据集中。

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "data" / "Fine_tuning_dataset" / "processed" / "Relation_error"

RULES_PATH = DATA_DIR / "not_predefined_relation_types_count_codex_claude_manual_tovscode.csv"
RELATION_ERROR_PATH = DATA_DIR / "Relation_error.jsonl"
TEMP_CORRECT_PATH = (
    DATA_DIR / "triples_baichuan_m3_Add_ID_Format_correct_Entity_correct_Relation_correct_temp.jsonl"
)
OUTPUT_PATH = (
    DATA_DIR / "triples_baichuan_m3_Add_ID_Format_correct_Entity_correct_Relation_correct.jsonl"
)

MATCH = "Match"
REVERSE = "Reverse"
DELETE = "Delete"
VALID_ACTIONS = {MATCH, REVERSE, DELETE}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="处理关系错误三元组，并将清洗结果合并到关系正确数据集中。",
        add_help=False,
    )
    parser.add_argument(
        "--rules-path",
        type=Path,
        default=RULES_PATH,
        help="人工映射规则 CSV 文件路径。",
    )
    parser.add_argument(
        "--relation-error-path",
        type=Path,
        default=RELATION_ERROR_PATH,
        help="待清洗的 relation 错误三元组 JSONL 文件路径。",
    )
    parser.add_argument(
        "--temp-correct-path",
        type=Path,
        default=TEMP_CORRECT_PATH,
        help="关系正确临时数据集 JSONL 文件路径。",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=OUTPUT_PATH,
        help="合并后的输出 JSONL 文件路径。",
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="显示帮助信息并退出。",
    )
    return parser.parse_args()


def load_rules(rules_path: Path) -> dict[str, tuple[str, str]]:
    rules: dict[str, tuple[str, str]] = {}

    with rules_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        required_columns = {"relation", "matching_manual_type", "matching_manual_relation"}
        missing_columns = required_columns - set(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(f"Rules CSV is missing columns: {sorted(missing_columns)}")

        for line_number, row in enumerate(reader, start=2):
            relation = row["relation"].strip()
            action = row["matching_manual_type"].strip()
            mapped_relation = row["matching_manual_relation"].strip()

            if not relation:
                raise ValueError(f"Empty relation in rules CSV at line {line_number}")
            if relation in rules:
                raise ValueError(f"Duplicate relation in rules CSV at line {line_number}: {relation}")
            if action not in VALID_ACTIONS:
                raise ValueError(
                    f"Unknown matching_manual_type in rules CSV at line {line_number}: {action}"
                )
            if action in {MATCH, REVERSE} and not mapped_relation:
                raise ValueError(
                    f"Missing matching_manual_relation for {action} at line {line_number}: {relation}"
                )

            rules[relation] = (action, mapped_relation)

    return rules


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as jsonl_file:
        for line_number, line in enumerate(jsonl_file, start=1):
            if not line.strip():
                continue
            try:
                yield line_number, json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} at line {line_number}: {exc}") from exc


def clean_relation_error_triples(
    relation_error_path: Path, rules: dict[str, tuple[str, str]]
) -> tuple[list[dict], Counter]:
    cleaned_triples: list[dict] = []
    stats: Counter = Counter()

    for line_number, triple in iter_jsonl(relation_error_path):
        relation = triple.get("relation")
        if relation not in rules:
            raise ValueError(
                f"No manual matching rule for relation at line {line_number}: {relation!r}"
            )

        action, mapped_relation = rules[relation]
        stats[action] += 1

        if action == DELETE:
            continue

        if action == REVERSE:
            triple["head"], triple["tail"] = triple["tail"], triple["head"]
            triple["head_type"], triple["tail_type"] = triple["tail_type"], triple["head_type"]

        triple["relation"] = mapped_relation
        cleaned_triples.append(triple)

    return cleaned_triples, stats


def merge_jsonl(temp_correct_path: Path, cleaned_triples: list[dict], output_path: Path) -> int:
    merged_total = 0

    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        for _, triple in iter_jsonl(temp_correct_path):
            output_file.write(json.dumps(triple, ensure_ascii=False) + "\n")
            merged_total += 1

        for triple in cleaned_triples:
            output_file.write(json.dumps(triple, ensure_ascii=False) + "\n")
            merged_total += 1

    return merged_total


def main() -> None:
    args = parse_args()

    rules = load_rules(args.rules_path)
    cleaned_triples, stats = clean_relation_error_triples(args.relation_error_path, rules)
    merged_total = merge_jsonl(args.temp_correct_path, cleaned_triples, args.output_path)

    print(f"rules_loaded: {len(rules)}")
    print(f"matched: {stats[MATCH]}")
    print(f"reversed: {stats[REVERSE]}")
    print(f"deleted: {stats[DELETE]}")
    print(f"cleaned_relation_error_triples: {len(cleaned_triples)}")
    print(f"merged_total: {merged_total}")
    print(f"output_path: {args.output_path}")


if __name__ == "__main__":
    main()
