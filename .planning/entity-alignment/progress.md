# Progress Log — 实体对齐 / 实体链接 / KG 构建

> 追加式日志，最新在底部；每完成一步追加一条。

- 2026-06-02 启动本计划（planning-with-files）。恢复上下文：上游三元组抽取已完成、baichuan-qlora 微调在远程跑（与本计划解耦）。
- 2026-06-02 数据画像实测：三元组 724,754 条 / 89 关系；U 型+反 U 型共 96 条待归并；已有 pos/neg_correlated（跨源接口）；第二批 distinct 实体 16.5 万 → 估计两批 20–30 万；THPA TSV ≈2.37GB；API.txt 298 keys。
- 2026-06-02 剖析参考仓库：MDKG=SapBERT+FAISS 链接公共本体（阈值 0.88/0.85）；KGLM=Jaccard+SBERT 两段式对齐（O(N²) 不适用本规模，思想保留）。
- 2026-06-02 外部调研：SapBERT 为生物医学 EL SOTA；大规模 ER 须 blocking。确定「link-first 混合 + 持久 registry + 增量」架构。
- 2026-06-02 建 `.planning/entity-alignment/` 三件套；切 `.active_plan` → entity-alignment（hook 改注入本计划，可逆）。
- 2026-06-02 用户拍板 D1–D4：D1 综合全量本体 / D2 官方 name+CURIE 主键 / D3 基因主键 ENSG·name 用符号 / D4 丢弃 Class2·Class3 且 Feature 不拆分。已写回 task_plan.md。
- 2026-06-02 **Phase 2a 完成**：脚本 `scripts/Entity_alignment/merge_relation_types.py`（argparse+中文help，默认非原地、可 dry-run）。归并 96 条（第一批64/第二批32）U型+反U型 → associated_with，输出 `*_Umerged.jsonl`。dry-run 复核：残留U型0、行数 423823/300931 不变、associated_with 66352/27850。
- （下一条）Phase 1 方案设计文档 + Phase 2b THPA 2.37GB 流式预处理（含 distinct 抽取、解析规则、翻译缓存）。待用户指示先做哪个 / 是否开跑重活。
