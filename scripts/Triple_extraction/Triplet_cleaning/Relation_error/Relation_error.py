# English: Split JSONL triples by predefined relation labels from the triple prompt.
# Chinese: Count relation frequency and split triples by predefined relations in the triple prompt.
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional


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
DEFAULT_ERROR_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Relation_error"
    / "Relation_error.jsonl"
)
DEFAULT_CORRECT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Relation_error"
    / "triples_baichuan_m3_Add_ID_Format_correct_Entity_correct_Relation_correct_temp.jsonl"
)
DEFAULT_STATISTICS_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Relation_error"
    / "Relationship_instance_statistics.csv"
)
DEFAULT_PREDEFINED_STATISTICS_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Relation_error"
    / "Relationship_instance_statistics_predefined_relation_types.csv"
)
DEFAULT_NOT_PREDEFINED_STATISTICS_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "Fine_tuning_dataset"
    / "processed"
    / "Relation_error"
    / "Relationship_instance_statistics_not_predefined_relation_types.csv"
)
DEFAULT_PROMPT = PROJECT_ROOT / "prompts" / "Triple_prompt.md"


def load_predefined_relations(prompt_path: Path) -> set[str]:
    """Load predefined relation labels from the relation table in Triple_prompt.md."""
    relations: set[str] = set()
    in_relation_section = False
    relation_pattern = re.compile(r"^\|\s*`([^`]+)`\s*\|")

    with prompt_path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped_line = line.strip()
            if stripped_line == "## Predefined Relation Types":
                in_relation_section = True
                continue

            if in_relation_section and stripped_line.startswith("## "):
                break

            if not in_relation_section:
                continue

            match = relation_pattern.match(stripped_line)
            if match:
                relations.add(match.group(1).strip())

    return relations


def count_relations(jsonl_path: Path) -> tuple[Counter[str], int, int]:
    """Count relation frequencies from a JSONL file."""
    relation_counter: Counter[str] = Counter()
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


def write_relation_statistics(
    statistics_output_path: Path,
    relation_counter: Counter[str],
    selected_relations: Optional[set[str]] = None,
) -> bool:
    """Write relation frequency statistics to a CSV file."""
    statistics_output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with statistics_output_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["relation", "count"])
            for relation, count in relation_counter.most_common():
                if selected_relations is not None and relation not in selected_relations:
                    continue
                writer.writerow([relation, count])
    except PermissionError:
        print(f"Permission denied while writing statistics file: {statistics_output_path}")
        return False

    return True


def split_by_predefined_relation(
    jsonl_path: Path,
    error_output_path: Path,
    correct_output_path: Path,
    predefined_relations: set[str],
) -> tuple[int, int, int]:
    """Write triples with undefined relations and triples with predefined relations."""
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

            relation = obj.get("relation")
            relation_is_predefined = (
                isinstance(relation, str) and relation.strip() in predefined_relations
            )

            if relation_is_predefined:
                correct_dst.write(raw_line + "\n")
                correct_lines += 1
            else:
                error_dst.write(raw_line + "\n")
                error_lines += 1

    return error_lines, correct_lines, invalid_lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Split triples by whether their relation labels are defined in the "
            "predefined relation table of Triple_prompt.md."
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
        help="Output JSONL path for triples containing low-frequency relations.",
    )
    parser.add_argument(
        "--correct-output",
        type=Path,
        default=DEFAULT_CORRECT_OUTPUT,
        help="Output JSONL path for triples with predefined relations.",
    )
    parser.add_argument(
        "--statistics-output",
        type=Path,
        default=DEFAULT_STATISTICS_OUTPUT,
        help="Output CSV path for relation frequency statistics.",
    )
    parser.add_argument(
        "--predefined-statistics-output",
        type=Path,
        default=DEFAULT_PREDEFINED_STATISTICS_OUTPUT,
        help="Output CSV path for predefined relation frequency statistics.",
    )
    parser.add_argument(
        "--not-predefined-statistics-output",
        type=Path,
        default=DEFAULT_NOT_PREDEFINED_STATISTICS_OUTPUT,
        help="Output CSV path for non-predefined relation frequency statistics.",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=DEFAULT_PROMPT,
        help="Triple prompt path containing the predefined relation table.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Input file does not exist: {args.input}")
        return

    if not args.prompt.exists():
        print(f"Prompt file does not exist: {args.prompt}")
        return

    predefined_relations = load_predefined_relations(args.prompt)
    if not predefined_relations:
        print(f"No predefined relations found in prompt file: {args.prompt}")
        return

    relation_counter, valid_lines, invalid_lines = count_relations(args.input)
    undefined_relations = set(relation_counter) - predefined_relations
    unused_predefined_relations = predefined_relations - set(relation_counter)

    write_relation_statistics(args.statistics_output, relation_counter)
    write_relation_statistics(
        args.predefined_statistics_output,
        relation_counter,
        predefined_relations,
    )
    write_relation_statistics(
        args.not_predefined_statistics_output,
        relation_counter,
        undefined_relations,
    )

    error_lines, correct_lines, split_invalid_lines = split_by_predefined_relation(
        args.input,
        args.error_output,
        args.correct_output,
        predefined_relations,
    )

    print(f"Input file: {args.input}")
    print(f"Prompt file: {args.prompt}")
    print(f"Valid records: {valid_lines}")
    print(f"Invalid records while counting: {invalid_lines}")
    print(f"Unique relations: {len(relation_counter)}")
    print(f"Predefined relations: {len(predefined_relations)}")
    print("\nAll relation frequencies, sorted descending:")
    for relation, count in relation_counter.most_common():
        print(f"{relation} {count}")

    print(f"Undefined relation count: {len(undefined_relations)}")
    print("Undefined relations, sorted ascending by count:")
    for relation, count in sorted(
        ((r, relation_counter[r]) for r in undefined_relations),
        key=lambda x: (x[1], x[0]),
    ):
        print(f"{relation} {count}")
    print(f"Unused predefined relation count: {len(unused_predefined_relations)}")
    print("Unused predefined relations, sorted alphabetically:")
    for relation in sorted(unused_predefined_relations):
        print(relation)
    print(f"Invalid records while splitting: {split_invalid_lines}")
    print(f"Undefined relation triples: {error_lines}")
    print(f"Predefined relation triples: {correct_lines}")
    print(f"Error output file: {args.error_output}")
    print(f"Correct output file: {args.correct_output}")
    print(f"Relation statistics file: {args.statistics_output}")
    print(f"Predefined relation statistics file: {args.predefined_statistics_output}")
    print(f"Non-predefined relation statistics file: {args.not_predefined_statistics_output}")


if __name__ == "__main__":
    main()
