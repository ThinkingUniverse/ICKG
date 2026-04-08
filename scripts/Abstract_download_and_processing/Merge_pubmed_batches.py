"""
合并两个时间段的 PubMed batch 文件：
  - data/pubmed_output/2021-2026/pubmed_batch_0001.json ~ 0140.json
  - data/pubmed_output/2016-2020/pubmed_batch_0141.json ~ 0250.json
处理规则：
  - 按 PMID 去重（保留首次出现的记录）
  - 删除 Abstract 为空或包含"的"的记录
  - 每条记录添加 Time、Batch、ID 字段（放在最前面）
  - 输出到 PubMed_abstract_2016_01_01_2026_03_31.json
"""

import json
from pathlib import Path

# 两个时间段的目录及对应 Time 标签，按处理顺序排列
SOURCES = [
    {
        "dir":     Path("data/pubmed_output/2021-2026"),
        "pattern": "pubmed_batch_*.json",
        "time":    "2021-2026",
    },
    {
        "dir":     Path("data/pubmed_output/2016-2020"),
        "pattern": "pubmed_batch_*.json",
        "time":    "2016-2020",
    },
]

OUTPUT_FILE = Path("data/pubmed_output/merge/PubMed_abstract_2016_01_01_2026_03_31.json")


def is_valid_abstract(abstract: str) -> bool:
    """Abstract 非空且不含中文"的"字则保留。"""
    if not abstract.strip():
        return False
    if "的" in abstract:
        return False
    return True


def main():
    seen_pmids: set[str] = set()
    merged:     list[dict] = []

    for source in SOURCES:
        batch_files = sorted(source["dir"].glob(source["pattern"]))
        print(f"\n[{source['time']}] Found {len(batch_files)} batch files in {source['dir']}")

        for batch_path in batch_files:
            batch_id = batch_path.stem.split("_")[-1]   # e.g. "0001"

            with open(batch_path, encoding="utf-8") as f:
                records = json.load(f)

            before = len(merged)
            skipped_dedup    = 0
            skipped_abstract = 0

            for rec in records:
                pmid = rec.get("PMID", "").strip()

                # ── 去重 ──
                if not pmid or pmid in seen_pmids:
                    skipped_dedup += 1
                    continue

                # ── Abstract 过滤 ──
                abstract = rec.get("Abstract", "")
                if not is_valid_abstract(abstract):
                    skipped_abstract += 1
                    seen_pmids.add(pmid)   # 仍标记为已见，防止从另一目录重复引入
                    continue

                seen_pmids.add(pmid)

                # Time / Batch / ID 放最前面，其余字段保持原顺序
                new_rec = {
                    "Time":  source["time"],
                    "Batch": batch_id,
                    "ID":    "",            # 占位，最后统一编号
                    **rec,
                }
                merged.append(new_rec)

            added = len(merged) - before
            print(
                f"  {batch_path.name}: {len(records)} total | "
                f"+{added} kept | "
                f"{skipped_dedup} dedup | "
                f"{skipped_abstract} abstract filtered"
            )

    # ── 统一填写 ID（1-based，按最终顺序） ──
    for idx, rec in enumerate(merged, start=1):
        rec["ID"] = str(idx)

    # ── 写出合并文件 ──
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(merged):,} unique valid records → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
