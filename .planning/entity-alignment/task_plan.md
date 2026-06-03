# Task Plan — 实体对齐 + 实体链接 + Neo4j 知识图谱构建

> Plan ID: entity-alignment ・ 创建 2026-06-02 ・ 语言中文
> 详细方法调研、本体下载地址、概念问答见 [findings.md](findings.md)；会话日志见 [progress.md](progress.md)
> 上游：三元组抽取已完成（[baichuan-qlora](../baichuan-qlora/task_plan.md) 微调在远程服务器进行中，与本计划解耦）

## 目标 (Goal)
把两类数据融合进 Neo4j 知识图谱，做到「同义实体唯一化 + 等价三元组聚合 + 跨源同一事实合并」，并固化为可对**未来推理新三元组**增量对齐的可复用管线。**质量优先于速度**。
- **数据 A：文献三元组** 724,754 条（第一批 423,823 + 第二批 300,931），字段 `ID1/ID2/PMID/head/head_type/relation/tail/tail_type/source_sentence/score`，89 种关系，全英文。
- **数据 B：THPA 关联结果** `THPA/lm_immune_vs_other_phenotypes_..._0.05.tsv`（≈2.37GB，20 列）。头实体=`Feature`（免疫细胞表型，英文），尾实体=`Other_phenotypes`（中/英/混合）。关系由 `Estimate` 方向定：>0 → `positively_correlated_with`，<0 → `negatively_correlated_with`。

## 核心设计决策（已调研，详见 findings.md §2–§4）
- **对齐 vs 链接分两步且互补**：先**实体链接**到公共本体（拿官方 name+CURIE），再对**残余**自有实体做**对齐聚类**并自铸 ID。链接命中即天然完成对齐（本体自带同义词表）。
- **嵌入/检索**：SapBERT（生物医学 EL 的 SOTA，最近邻即可）+ FAISS；中文尾实体先翻译成英文，统一进英文向量空间。中文翻译走有道 NMT / Baichuan-M3，**只翻唯一值并建缓存**。
- **必须 blocking**：唯一实体 ~20–30 万（仅第二批就 16.5 万），禁止 O(N²) 两两比较（参考仓库 KGLM 的 `align_entities` 在本数据规模不可用）。
- **规范命名**：链接成功 → 采用本体官方 name + CURIE（如 `alpha-beta T cell` / `CL:0000789`）；自有实体 → 自铸 `ICKG:0000001` 简短稳定 ID。原始各种写法存为 `synonyms` 属性。
- **持久实体注册表 (entity registry)** = 增量对齐的核心产物：`surface_form → canonical_id`，附 FAISS 向量索引；新三元组复用它，命中则复用、未命中则新链接/铸号并追加。
- **关系/实体属性**：见 findings.md §6 的属性映射表。

## 阶段总览
| # | 阶段 | 状态 |
|---|------|------|
| 0 | 启动脚手架：建计划、切 `.active_plan`、数据画像（distinct 计数） | ✅ complete（Neo4j 连通性验证推迟到 Phase 7） |
| 1 | 方法调研定稿 + 本体选型 + 嵌入/分块方案 + 架构设计文档 | ⏸️ pending |
| 2a | 三元组预处理：两批 U 型/反 U 型(96 条) 归并入 `associated_with` | ✅ complete（→ `*_Umerged.jsonl`；残留0/行数不变；脚本 `scripts/Entity_alignment/merge_relation_types.py`） |
| 2b | THPA 2.37GB 流式预处理：抽 distinct Feature/Other_phenotypes、解析规则、翻译缓存、产出规范化关联三元组 | ⏸️ pending |
| 3 | 实体规范化 + 全局实体清册 + blocking 候选生成 | ⏸️ pending |
| 4 | 实体链接到公共本体（下载本体→SapBERT/FAISS 嵌入→链接→分配官方 name+CURIE→抽检） | ⏸️ pending |
| 5 | 残余实体对齐聚类 + 自铸 ID + 构建持久 entity registry（覆盖三种对齐范围） | ⏸️ pending |
| 6 | 三元组聚合融合：套用 registry → 聚合等价三元组(PMID/句子/score/出现次数) → 跨源同一事实合并 → 挂属性 | ⏸️ pending |
| 7 | Neo4j schema(约束/索引) + 批量导入 + 校验查询 | ⏸️ pending |
| 8 | 增量管线固化：新推理三元组对齐脚本 + 文档 | ⏸️ pending |
| 9 | 质量评估验收：抽样 P/R、阈值调优、最终报告 | ⏸️ pending |

## 已确认的关键决策（2026-06-02 用户拍板）
- [x] **D1 本体集成范围 = 一次性综合全量**：CL / Ensembl·HGNC / NCBI Taxonomy / UBERON / MONDO / HPO / EFO / ChEBI / UMLS 全部接入。
- [x] **D2 链接命名 = 官方 name+CURIE 作主名/主键**（如 `alpha-beta T cell` / `CL:0000789`），原始写法存 `synonyms`。
- [x] **D3 基因实体 = 主键 ENSG、name 用基因符号**（id=ENSG…, name=ATP6V1C1, unit=log2FPKM 作属性）。
- [x] **D4 丢弃 `Class2`/`Class3`**；`Feature` 作单一节点不拆分（属性仅 Type/Class/Cell + 原始 Immunophenotype）。

## 代码与数据落地
- **本地操作**（CLAUDE.local.md 默认；Neo4j 在 localhost；2.37GB TSV 在本地 THPA/）。执行前 `conda activate ickg`。
- 脚本目录拟：`scripts/Entity_alignment/`；中间产物拟：`data/Entity_alignment/`。所有脚本走 argparse、中文 help。

## Errors Encountered
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| （暂无） | | |
