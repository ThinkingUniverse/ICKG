import json
import random
import re
from pathlib import Path

INPUT_PATH = Path("data/pubmed_output/merge/PubMed_abstract_2016_01_01_2026_03_31.json")
OUTPUT_DIR = Path("data/pubmed_output/random_sampling")
OUTPUT_PREFIX = "PubMed_abstract_sampled_5000_"
OUTPUT_SUFFIX = ".json"
SAMPLE_SIZE = 5000
OUTPUT_PATTERN = re.compile(r"^PubMed_abstract_sampled_5000_(\d+)\.json$")


def normalize_pmid(record):
    pmid = record.get("PMID")
    if pmid is None:
        return ""
    pmid_str = str(pmid).strip()
    return pmid_str


def load_json_array(file_path):
    with file_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, list):
        raise ValueError(f"JSON root must be a list: {file_path}")

    return payload


def collect_history_state(output_dir):
    used_pmids = set()
    matched_files = []
    max_index = 0
    history_missing_pmid = 0

    for path in output_dir.iterdir():
        if not path.is_file():
            continue
        match = OUTPUT_PATTERN.match(path.name)
        if not match:
            continue

        matched_files.append(path)
        max_index = max(max_index, int(match.group(1)))

    # Keep deterministic order to make debugging easier.
    matched_files.sort(key=lambda p: p.name)

    for path in matched_files:
        try:
            history_data = load_json_array(path)
        except Exception as exc:
            raise RuntimeError(f"Failed to parse history file: {path}") from exc

        for record in history_data:
            if not isinstance(record, dict):
                continue
            pmid = normalize_pmid(record)
            if not pmid:
                history_missing_pmid += 1
                continue
            used_pmids.add(pmid)

    return {
        "matched_files": matched_files,
        "max_index": max_index,
        "used_pmids": used_pmids,
        "history_missing_pmid": history_missing_pmid,
    }


def build_candidate_pool(source_data, used_pmids):
    candidates = []
    seen_candidate_pmids = set()
    source_missing_pmid = 0
    source_duplicate_pmid = 0

    for record in source_data:
        if not isinstance(record, dict):
            continue

        pmid = normalize_pmid(record)
        if not pmid:
            source_missing_pmid += 1
            continue

        if pmid in used_pmids:
            continue

        if pmid in seen_candidate_pmids:
            source_duplicate_pmid += 1
            continue

        seen_candidate_pmids.add(pmid)
        candidates.append(record)

    return candidates, source_missing_pmid, source_duplicate_pmid


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    history_state = collect_history_state(OUTPUT_DIR)
    next_index = history_state["max_index"] + 1

    source_data = load_json_array(INPUT_PATH)
    candidate_pool, source_missing_pmid, source_duplicate_pmid = build_candidate_pool(
        source_data, history_state["used_pmids"]
    )

    sample_count = min(SAMPLE_SIZE, len(candidate_pool))
    if sample_count == 0:
        sampled_data = []
    else:
        sampled_data = random.sample(candidate_pool, sample_count)

    output_path = OUTPUT_DIR / f"{OUTPUT_PREFIX}{next_index}{OUTPUT_SUFFIX}"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(sampled_data, f, ensure_ascii=False, indent=2)

    print(f"[INFO] 源数据总量: {len(source_data)}")
    print(f"[INFO] 历史样本文件数: {len(history_state['matched_files'])}")
    print(f"[INFO] 历史已抽取唯一 PMID 数: {len(history_state['used_pmids'])}")
    print(f"[INFO] 历史样本中缺失 PMID 条数: {history_state['history_missing_pmid']}")
    print(f"[INFO] 去重后候选池大小: {len(candidate_pool)}")
    print(f"[INFO] 源数据中缺失 PMID 条数: {source_missing_pmid}")
    print(f"[INFO] 源数据中重复 PMID 条数: {source_duplicate_pmid}")

    if sample_count < SAMPLE_SIZE:
        print(
            f"[WARN] 去重后可抽样条数不足 {SAMPLE_SIZE}，本次仅输出 {sample_count} 条。"
        )

    print(f"[INFO] 本次输出文件编号: {next_index}")
    print(f"[INFO] 本次抽取数据量: {len(sampled_data)}")
    print(f"[SUCCESS] 已保存至: {output_path}")


if __name__ == "__main__":
    main()