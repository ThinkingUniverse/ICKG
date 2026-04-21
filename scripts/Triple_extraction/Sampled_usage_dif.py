# 中文说明：
# 本脚本用于读取 data/pubmed_output/random_sampling 目录下
# PubMed_abstract_sampled_5000_1.json 到 PubMed_abstract_sampled_5000_8.json 中的所有 PMID，
# 与 data/Fine_tuning_dataset/triples_usage.jsonl 中记录的所有 PMID 分别去重后进行比较，
# 输出两个集合共有的 PMID 数量、各自特有的 PMID 数量，并打印各自特有的具体 PMID，
# 同时将共有 PMID 写入 data/Fine_tuning_dataset/Sampled_usage_intersection.txt。
#
# English description:
# This script reads all PMIDs from PubMed_abstract_sampled_5000_1.json through
# PubMed_abstract_sampled_5000_8.json under data/pubmed_output/random_sampling,
# compares the de-duplicated PMID set with the de-duplicated PMIDs recorded in
# data/Fine_tuning_dataset/triples_usage.jsonl, then prints the number of shared
# PMIDs, the number of PMIDs unique to each source, the concrete unique PMIDs,
# and writes the shared PMIDs to data/Fine_tuning_dataset/Sampled_usage_intersection.txt.

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RANDOM_SAMPLING_DIR = PROJECT_ROOT / "data" / "pubmed_output" / "random_sampling"
TRIPLES_USAGE_FILE = PROJECT_ROOT / "data" / "Fine_tuning_dataset" / "triples_usage.jsonl"
INTERSECTION_OUTPUT_FILE = PROJECT_ROOT / "data" / "Fine_tuning_dataset" / "Sampled_usage_intersection.txt"


def normalize_pmid(value):
    """Return a clean PMID string, or None when the value is empty."""
    if value is None:
        return None

    pmid = str(value).strip()
    return pmid or None


def sort_pmids(pmids):
    """Sort numeric PMIDs numerically while still supporting non-numeric values."""
    return sorted(pmids, key=lambda pmid: (not pmid.isdigit(), int(pmid) if pmid.isdigit() else pmid))


def load_sampled_pmids():
    sampled_pmids = set()

    for index in range(1, 9):
        json_file = RANDOM_SAMPLING_DIR / f"PubMed_abstract_sampled_5000_{index}.json"
        with json_file.open("r", encoding="utf-8") as file:
            records = json.load(file)

        for record in records:
            pmid = normalize_pmid(record.get("PMID"))
            if pmid:
                sampled_pmids.add(pmid)

    return sampled_pmids


def load_usage_pmids():
    usage_pmids = set()

    with TRIPLES_USAGE_FILE.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON at line {line_number}: {error}") from error

            pmid = normalize_pmid(record.get("PMID"))
            if pmid:
                usage_pmids.add(pmid)

    return usage_pmids


def print_pmid_list(title, pmids):
    print(title)
    if not pmids:
        print("  None")
        return

    for pmid in sort_pmids(pmids):
        print(f"  {pmid}")


def write_pmid_list(output_file, pmids):
    sorted_pmids = sort_pmids(pmids)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open("w", encoding="utf-8", newline="\n") as file:
        for pmid in sorted_pmids:
            file.write(f"{pmid}\n")


def main():
    sampled_pmids = load_sampled_pmids()
    usage_pmids = load_usage_pmids()

    shared_pmids = sampled_pmids & usage_pmids
    sampled_only_pmids = sampled_pmids - usage_pmids
    usage_only_pmids = usage_pmids - sampled_pmids
    write_pmid_list(INTERSECTION_OUTPUT_FILE, shared_pmids)

    print("PMID comparison summary")
    print(f"Sampled JSON unique PMID count: {len(sampled_pmids)}")
    print(f"Triples usage unique PMID count: {len(usage_pmids)}")
    print(f"Shared PMID count: {len(shared_pmids)}")
    print(f"Only in sampled JSON count: {len(sampled_only_pmids)}")
    print(f"Only in triples usage count: {len(usage_only_pmids)}")
    print()

    print_pmid_list("PMIDs only in sampled JSON:", sampled_only_pmids)
    print()
    print_pmid_list("PMIDs only in triples usage:", usage_only_pmids)
    print()
    print(f"Shared PMIDs written to: {INTERSECTION_OUTPUT_FILE}")


if __name__ == "__main__":
    main()
