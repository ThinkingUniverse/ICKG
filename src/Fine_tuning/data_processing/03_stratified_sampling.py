#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Stratified sampling of N PMIDs with relation-coverage and rebalance constraints.
# 在三元组数分桶 + 关系覆盖保证 + 关系再平衡（含 increases 上限、含 associated_with 下限）约束下分层采样 N 个 PMID。
"""
输入：pmid_to_triples.jsonl（02 步产物）
输出：
  - sampled_5000_pmids.txt   每行一个 PMID
  - sampling_stats.json      采样前后实体/关系/三元组数/score 的分布对照

采样规则全部读自 data_config.yaml:
  - triple_count_buckets   : 按三元组数分桶比例
  - max_triples_per_abstract : 每篇截断阈值（按 score 降序保留前 N 条）
  - min_triples_per_abstract : 低于此值的 PMID 排除
  - min_pmid_per_relation  : 每种关系至少出现在多少篇训练样本中
  - rebalance.max_share / min_share : 含某关系的 PMID 占比上下限

多 pass 采样：
  Pass A — 低频关系强制覆盖（保证 min_pmid_per_relation）
  Pass B — 含 associated_with 的 PMID 满足 min_share
  Pass C — 随机填满各分桶配额，跳过会触发 max_share 上限的 PMID
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import yaml


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="分层采样 N 个 PMID，含关系覆盖与再平衡约束")
    parser.add_argument(
        "--config", "-c",
        default="src/Fine_tuning/configs/data_config.yaml",
        help="数据处理配置 YAML 路径",
    )
    parser.add_argument(
        "--input", "-i", default=None,
        help="输入 pmid_to_triples.jsonl，留空则取 output_dir + files.pmid_to_triples",
    )
    parser.add_argument(
        "--output-pmids", "-o", default=None,
        help="输出采样 PMID 列表 txt，留空则取 output_dir + files.sampled_pmids",
    )
    parser.add_argument(
        "--output-stats", default=None,
        help="输出采样分布报告 json，留空则取 output_dir + files.sampling_stats",
    )
    parser.add_argument(
        "--seed", "-s", type=int, default=None,
        help="随机种子，留空则取配置中 split.random_seed",
    )
    parser.add_argument(
        "--n-samples", "-n", type=int, default=None,
        help="采样总数，留空则取 sampling.total_samples",
    )
    return parser.parse_args()


# --------------------------------------------------------------------------- #
# 工具函数                                                                     #
# --------------------------------------------------------------------------- #

def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_paths(args: argparse.Namespace, cfg: dict) -> tuple[Path, Path, Path]:
    repo_root = Path(__file__).resolve().parents[3]
    out_dir = repo_root / cfg["output_dir"]

    input_path = Path(args.input) if args.input else out_dir / cfg["files"]["pmid_to_triples"]
    pmids_path = Path(args.output_pmids) if args.output_pmids else out_dir / cfg["files"]["sampled_pmids"]
    stats_path = Path(args.output_stats) if args.output_stats else out_dir / cfg["files"]["sampling_stats"]

    for p in (pmids_path, stats_path):
        p.parent.mkdir(parents=True, exist_ok=True)
    return input_path, pmids_path, stats_path


def assign_bucket(n_triples: int, buckets: list[dict]) -> str | None:
    """根据 n_triples 把 PMID 分到桶中，未命中返回 None"""
    for b in buckets:
        if b["min"] <= n_triples <= b["max"]:
            return b["name"]
    return None


def truncate_triples(triples: list[dict], max_keep: int) -> list[dict]:
    """按 score 降序保留前 max_keep 条；triples 已在 02 步排好序"""
    if len(triples) <= max_keep:
        return triples
    return triples[:max_keep]


def distribute_quota_across_buckets(
    target: int, bucket_quotas: dict[str, int]
) -> dict[str, int]:
    """按各桶剩余配额比例分摊 target 名额"""
    remaining = sum(bucket_quotas.values())
    if remaining == 0:
        return {k: 0 for k in bucket_quotas}
    assigned = {
        k: int(round(target * (v / remaining))) for k, v in bucket_quotas.items()
    }
    # 修正舍入误差
    diff = target - sum(assigned.values())
    if diff != 0:
        # 把差额加到名额最大的桶
        biggest = max(assigned, key=lambda k: bucket_quotas[k])
        assigned[biggest] += diff
    return assigned


# --------------------------------------------------------------------------- #
# 主流程                                                                       #
# --------------------------------------------------------------------------- #

def main() -> None:
    args = parse_args()
    cfg = load_config(Path(args.config))
    input_path, pmids_path, stats_path = resolve_paths(args, cfg)

    seed = args.seed if args.seed is not None else cfg["split"]["random_seed"]
    rng = random.Random(seed)

    sampling_cfg = cfg["sampling"]
    total_n = args.n_samples if args.n_samples is not None else sampling_cfg["total_samples"]
    buckets_cfg = sampling_cfg["triple_count_buckets"]
    max_triples = sampling_cfg["max_triples_per_abstract"]
    min_triples = sampling_cfg["min_triples_per_abstract"]
    min_pmid_per_rel = sampling_cfg["min_pmid_per_relation"]
    max_share = sampling_cfg.get("rebalance", {}).get("max_share", {}) or {}
    min_share = sampling_cfg.get("rebalance", {}).get("min_share", {}) or {}

    print(f"[信息] 输入：{input_path}")
    print(f"[信息] 目标采样：{total_n} 篇；seed={seed}")

    # ------------------------------------------------------------------ #
    # 1. 加载全部 PMID 记录，做截断、过滤、分桶                              #
    # ------------------------------------------------------------------ #
    pmid2triples: dict[str, list[dict]] = {}
    pmid2bucket:  dict[str, str] = {}
    pmid2relset:  dict[str, set[str]] = {}
    bucket_pool:  dict[str, list[str]] = defaultdict(list)
    n_total_input = 0
    n_below_min = 0

    with open(input_path, "r", encoding="utf-8") as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            n_total_input += 1
            triples = rec.get("triples", [])
            n_tri = len(triples)
            if n_tri < min_triples:
                n_below_min += 1
                continue

            triples = truncate_triples(triples, max_triples)
            pmid = rec["PMID"]
            bucket = assign_bucket(len(triples), buckets_cfg)
            if bucket is None:
                continue

            pmid2triples[pmid] = triples
            pmid2bucket[pmid] = bucket
            pmid2relset[pmid] = {t["relation"] for t in triples}
            bucket_pool[bucket].append(pmid)

    print(f"[加载] 候选 PMID：{n_total_input:,} → 进入分桶池 {len(pmid2triples):,} "
          f"（剔除 n_triples<{min_triples} 的 {n_below_min:,} 篇）")
    for b in buckets_cfg:
        print(f"   桶 {b['name']}  ({b['min']}-{b['max']} 条三元组)  候选 = {len(bucket_pool[b['name']]):,}")

    # ------------------------------------------------------------------ #
    # 2. 计算各桶配额                                                      #
    # ------------------------------------------------------------------ #
    bucket_quota = {b["name"]: int(round(b["ratio"] * total_n)) for b in buckets_cfg}
    # 修正配额加和
    diff = total_n - sum(bucket_quota.values())
    if diff != 0:
        first = buckets_cfg[0]["name"]
        bucket_quota[first] += diff
    print(f"[配额] 各桶名额：{bucket_quota}")

    # ------------------------------------------------------------------ #
    # 3. 关系反向索引                                                      #
    # ------------------------------------------------------------------ #
    rel2pmids: dict[str, list[str]] = defaultdict(list)
    for pmid, rels in pmid2relset.items():
        for r in rels:
            rel2pmids[r].append(pmid)
    print(f"[索引] 共出现关系类型 {len(rel2pmids)} 种")

    # ------------------------------------------------------------------ #
    # 4. 多 pass 采样                                                      #
    # ------------------------------------------------------------------ #
    selected: set[str] = set()
    # 各桶剩余配额（实时扣减）
    bucket_remaining = dict(bucket_quota)
    # 含某关系的已选数（用于检查 max_share / min_share）
    rel_count_selected: Counter[str] = Counter()

    def can_add(pmid: str, enforce_max_share: bool = True) -> bool:
        """检查添加这个 PMID 是否会违反 max_share 上限"""
        if pmid in selected:
            return False
        b = pmid2bucket[pmid]
        if bucket_remaining[b] <= 0:
            return False
        if not enforce_max_share:
            return True
        for r, max_ratio in max_share.items():
            if r in pmid2relset[pmid]:
                if (rel_count_selected[r] + 1) / total_n > max_ratio:
                    return False
        return True

    def commit(pmid: str) -> None:
        """正式纳入采样"""
        selected.add(pmid)
        bucket_remaining[pmid2bucket[pmid]] -= 1
        for r in pmid2relset[pmid]:
            rel_count_selected[r] += 1

    # ---- Pass A：低频关系强制覆盖 ----
    print("\n[Pass A] 低频关系强制覆盖 ...")
    rel_order = sorted(rel2pmids.keys(), key=lambda r: len(rel2pmids[r]))  # 从最稀缺开始
    forced_added = 0
    for rel in rel_order:
        need = min_pmid_per_rel - rel_count_selected[rel]
        if need <= 0:
            continue
        candidates = [p for p in rel2pmids[rel] if p not in selected]
        rng.shuffle(candidates)
        # 把 need 名额按桶剩余比例分配（如果某桶满了就跳过该桶的候选）
        for pmid in candidates:
            if rel_count_selected[rel] >= min_pmid_per_rel:
                break
            # Pass A 不强制 max_share（覆盖优先）
            if can_add(pmid, enforce_max_share=False):
                commit(pmid)
                forced_added += 1
    print(f"   Pass A 共加入 {forced_added:,} 篇；当前已采 {len(selected):,}")

    # ---- Pass B：含 associated_with 的 PMID 达成 min_share ----
    print("\n[Pass B] 满足 min_share（如 associated_with ≥ 35%）...")
    pass_b_added = 0
    for rel, min_ratio in min_share.items():
        need_count = int(round(min_ratio * total_n)) - rel_count_selected[rel]
        if need_count <= 0:
            continue
        candidates = [p for p in rel2pmids.get(rel, []) if p not in selected]
        rng.shuffle(candidates)
        for pmid in candidates:
            if rel_count_selected[rel] >= int(round(min_ratio * total_n)):
                break
            if can_add(pmid, enforce_max_share=True):
                commit(pmid)
                pass_b_added += 1
    print(f"   Pass B 共加入 {pass_b_added:,} 篇；当前已采 {len(selected):,}")

    # ---- Pass C：随机填满剩余配额 ----
    print("\n[Pass C] 随机填满剩余配额 ...")
    pass_c_added = 0
    for b in buckets_cfg:
        bname = b["name"]
        pool = [p for p in bucket_pool[bname] if p not in selected]
        rng.shuffle(pool)
        for pmid in pool:
            if bucket_remaining[bname] <= 0:
                break
            if can_add(pmid, enforce_max_share=True):
                commit(pmid)
                pass_c_added += 1
    print(f"   Pass C 共加入 {pass_c_added:,} 篇；当前已采 {len(selected):,}")

    # ---- Pass D（应急回填）：若总数仍未满，放宽 max_share，仅保证桶剩余配额 ----
    if len(selected) < total_n:
        print("\n[Pass D] 应急回填（放宽 max_share）...")
        d_added = 0
        for b in buckets_cfg:
            bname = b["name"]
            pool = [p for p in bucket_pool[bname] if p not in selected]
            rng.shuffle(pool)
            for pmid in pool:
                if bucket_remaining[bname] <= 0:
                    break
                if can_add(pmid, enforce_max_share=False):
                    commit(pmid)
                    d_added += 1
        print(f"   Pass D 应急加入 {d_added:,} 篇；最终采 {len(selected):,}")

    # ------------------------------------------------------------------ #
    # 5. 输出 sampled PMID 列表                                            #
    # ------------------------------------------------------------------ #
    selected_sorted = sorted(selected)  # 升序便于人工查阅
    with open(pmids_path, "w", encoding="utf-8", newline="\n") as f:
        for pmid in selected_sorted:
            f.write(pmid + "\n")
    print(f"\n[完成] 采样 PMID → {pmids_path}（共 {len(selected_sorted):,} 篇）")

    # ------------------------------------------------------------------ #
    # 6. 生成 sampling_stats.json                                          #
    # ------------------------------------------------------------------ #
    stats = build_stats(
        selected_pmids=selected,
        pmid2triples=pmid2triples,
        pmid2bucket=pmid2bucket,
        bucket_quota=bucket_quota,
        rel2pmids=rel2pmids,
        min_share=min_share,
        max_share=max_share,
        min_pmid_per_rel=min_pmid_per_rel,
        total_n=total_n,
    )
    with open(stats_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"[完成] 采样分布报告 → {stats_path}")

    # 控制台简明摘要
    print("\n=== 关系再平衡核对 ===")
    for r, ratio in {**max_share, **min_share}.items():
        n_sel = stats["relation_in_selected_pmids"].get(r, 0)
        print(f"   {r:30s}  {n_sel:5d}/{total_n}  ({n_sel/total_n:.2%})  目标={ratio}")
    print("=== 低频关系覆盖核对（< min_pmid_per_relation 即异常）===")
    abnormal = {r: c for r, c in stats["relation_in_selected_pmids"].items() if c < min_pmid_per_rel}
    if abnormal:
        print(f"   仍有 {len(abnormal)} 种关系覆盖不足：{abnormal}")
    else:
        print(f"   所有 {len(stats['relation_in_selected_pmids'])} 种关系均 ≥ {min_pmid_per_rel} 篇 ✅")


def build_stats(
    selected_pmids: set[str],
    pmid2triples: dict[str, list[dict]],
    pmid2bucket: dict[str, str],
    bucket_quota: dict[str, int],
    rel2pmids: dict[str, list[str]],
    min_share: dict[str, float],
    max_share: dict[str, float],
    min_pmid_per_rel: int,
    total_n: int,
) -> dict:
    """统计采样后的实体/关系/三元组数/score 分布等"""
    entity_counter: Counter[str] = Counter()
    relation_triple_counter: Counter[str] = Counter()       # 关系出现的三元组次数
    relation_pmid_counter: Counter[str] = Counter()         # 含某关系的 PMID 数
    score_counter: Counter[int] = Counter()                 # score 分桶（每 10 分）
    n_triples_per_pmid: list[int] = []
    bucket_in_selected: Counter[str] = Counter()

    for pmid in selected_pmids:
        triples = pmid2triples[pmid]
        n_triples_per_pmid.append(len(triples))
        bucket_in_selected[pmid2bucket[pmid]] += 1
        seen_rel = set()
        for t in triples:
            entity_counter[t["head_type"]] += 1
            entity_counter[t["tail_type"]] += 1
            relation_triple_counter[t["relation"]] += 1
            seen_rel.add(t["relation"])
            score_counter[(int(t["score"]) // 10) * 10] += 1
        for r in seen_rel:
            relation_pmid_counter[r] += 1

    stats = {
        "config_summary": {
            "total_n": total_n,
            "bucket_quota": bucket_quota,
            "min_pmid_per_relation": min_pmid_per_rel,
            "rebalance_min_share": min_share,
            "rebalance_max_share": max_share,
        },
        "actual_selected": len(selected_pmids),
        "bucket_distribution": dict(bucket_in_selected),
        "triples_per_pmid": {
            "min": min(n_triples_per_pmid),
            "max": max(n_triples_per_pmid),
            "mean": round(sum(n_triples_per_pmid) / len(n_triples_per_pmid), 2),
            "total": sum(n_triples_per_pmid),
        },
        "entity_type_distribution_in_triples": dict(entity_counter.most_common()),
        "relation_distribution_in_triples": dict(relation_triple_counter.most_common()),
        "relation_in_selected_pmids": dict(relation_pmid_counter.most_common()),
        "score_distribution_bin10": dict(sorted(score_counter.items())),
    }
    return stats


if __name__ == "__main__":
    main()
