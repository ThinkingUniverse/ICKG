"""
合并 pubmed_batch_0001.json ~ pubmed_batch_0140.json
- 按 PMID 去重（保留首次出现的记录）
- 每条记录添加 Download、Batch、ID 字段（放在最前面）
- 输出到 PubMed_abstract_2021_01_01_2026_03_31.json
"""

import json
from pathlib import Path

INPUT_DIR   = Path("data/pubmed_output")
OUTPUT_FILE = Path("data/pubmed_output/PubMed_abstract_2021_01_01_2026_03_31.json")

def main():
    # ── 1. 收集所有 batch 文件，按文件名排序 ──
    batch_files = sorted(INPUT_DIR.glob("pubmed_batch_*.json"))
    print(f"Found {len(batch_files)} batch files.")

    seen_pmids: set[str] = set()
    merged:     list[dict] = []

    # ── 2. 逐文件读取、去重、追加 ──
    for batch_path in batch_files:
        # 从文件名提取批次号，如 "pubmed_batch_0001.json" → "0001"
        batch_id = batch_path.stem.split("_")[-1]  # e.g. "0001"

        with open(batch_path, encoding="utf-8") as f:
            records = json.load(f)

        before = len(merged)
        for rec in records:
            pmid = rec.get("PMID", "").strip()
            if not pmid or pmid in seen_pmids:
                continue
            seen_pmids.add(pmid)

            # 新记录：Download / Batch / ID 放最前面，其余字段保持原顺序
            new_rec = {
                "Download": "1",
                "Batch":    batch_id,
                "ID":       "",          # 占位，统一编号在最后一步填写
                **rec,
            }
            merged.append(new_rec)

        added = len(merged) - before
        print(f"  {batch_path.name}: {len(records)} records, {added} added after dedup")

    # ── 3. 统一填写 ID（1-based，按最终顺序） ──
    for idx, rec in enumerate(merged, start=1):
        rec["ID"] = str(idx)

    # ── 4. 写出合并文件 ──
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\nDone. {len(merged):,} unique records → {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
