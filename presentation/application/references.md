<!--
ICKG Application Blueprint — Unified References
免疫细胞知识图谱应用蓝图 — 统一参考文献列表
-->

# 参考文献统一列表

> 共收录 **34 篇**核心文献，按 8 大主题 + 项目核心论文分组。每篇仅附一个最权威的可点击链接（优先 DOI，次之 PMID/arXiv）。⭐ 标记为 **must-read** 必读文献（共 16 篇）。

---

## 主题 1 · 免疫学知识图谱的构建与已发表应用

1. [Atallah-2020] [**ImmunoGlobe: enabling systems immunology with a manually curated intercellular immune interaction network**](https://pubmed.ncbi.nlm.nih.gov/32778050/). *BMC Bioinformatics*. 首个手工策划的免疫细胞间相互作用图谱，可视作 ICKG 在结构上的"前辈样板"。
2. [Shao-2021] [**CellTalkDB: a manually curated database of ligand-receptor interactions in humans and mice**](https://pubmed.ncbi.nlm.nih.gov/33147626/). *Brief Bioinform*. 提供高质量人/鼠配体-受体先验，是 ICKG 中 `protein/cytokine` 节点边集的事实标准基准。
3. [Shao-2022] [**Knowledge-graph-based cell-cell communication inference for spatially resolved transcriptomic data with SpaTalk**](https://pubmed.ncbi.nlm.nih.gov/35908020/). *Nat Commun*. 首次明确用 KG 推理方法在空间转录组上推断细胞通讯，验证 KG 思路对免疫微环境建模的实用价值。
4. [Olbei-2021] [**CytokineLink: a cytokine communication map to analyse immune responses – case studies in IBD and COVID-19**](https://doi.org/10.3390/cells10092242). *Cells*. 以细胞因子为枢纽的免疫通讯图，并演示其在 IBD 和 COVID-19 中的临床解释能力。
5. ⭐ [Cui-2024] [**Dictionary of immune responses to cytokines at single-cell resolution**](https://doi.org/10.1038/s41586-023-06816-9). *Nature*. 在单细胞分辨率上系统建立"细胞因子-免疫细胞应答"字典，是 ICKG 实体/关系本体设计的权威参考。

---

## 主题 2 · 知识图谱用于癌症免疫治疗响应预测（旗舰场景 2.3）

6. ⭐⭐ [Zhao-2023] [**Biological knowledge graph-guided investigation of immune therapy response in cancer with graph neural network**](https://doi.org/10.1093/bib/bbad023). *Brief Bioinform*. KG-引导 GNN 框架在多癌种上预测 ICI 响应并给出生物学可解释路径，最贴合 ICKG 直接迁移的工作。
7. ⭐⭐ [Jiang-2024] [**IRnet: Immunotherapy response prediction using pathway knowledge-informed graph neural network**](https://doi.org/10.1016/j.jare.2024.07.036). *J Adv Res*. 通路图 GNN 预测 ICI 响应，并提供 3 层级解释（基因/通路/患者）。
8. [Liu-2025-TCR] [**CKG-TPI: integrating collaborative knowledge graph with sequence interactions for TCR-peptide binding specificity**](https://doi.org/10.1093/bib/bbaf486). *Brief Bioinform*. 协同 KG 用于 TCR-肽结合预测，可拓展到 neoantigen 免疫治疗。
9. [Liu-2023-TMB] [**Biologically informed graph neural network for tumor mutation burden prediction and immunotherapy pathway analysis in gastric cancer**](https://doi.org/10.1016/j.csbj.2023.09.021). *Comput Struct Biotechnol J*. 通路图 GNN 在胃癌中预测 TMB 状态并识别 TLR、DNA 修复通路为 ICI 联合靶点。
10. [Ye-2025] [**Integration of GNN and transcriptomics for immunotherapy response and prognosis in skin melanoma**](https://doi.org/10.1186/s12885-025-13611-4). *BMC Cancer*. 把 GNN 输出转为 responseScore 临床特征，并与 TME 紧密关联。

---

## 主题 3 · KG embedding + 临床特征联合用于疾病风险/诊断预测（旗舰场景 2.1）

11. ⭐⭐ [Gao-2025] [**Large language model powered knowledge graph construction for mental health exploration**](https://doi.org/10.1038/s41467-025-62781-z). *Nat Commun*. MDKG 范式：RDF2Vec 200d → PheCode 映射 → AUC 0.82-0.89；**本蓝图 2.1/2.4 的方法学母本**。
12. ⭐ [Chandak-2023] [**Building a knowledge graph to enable precision medicine (PrimeKG)**](https://doi.org/10.1038/s41597-023-01960-3). *Sci Data*. 整合 20 个高质量资源、覆盖 17,080 种疾病的多模态精准医学 KG，是后续临床嵌入任务的标杆数据底座。
13. [Morris-2023] [**The Scalable Precision Medicine Open Knowledge Engine (SPOKE)**](https://doi.org/10.1093/bioinformatics/btad080). *Bioinformatics*. 27M 节点、53M 边的精准医学 KG，已被多项临床研究用于将患者电子档案 embedding 化做风险预测。
14. ⭐ [Wang-2026] [**Knowledge-graph embeddings for osteoarthritis candidate prediction**](https://doi.org/10.1038/s41746-025-02290-x). *npj Digit Med*. 用 KGE 在真实临床队列上预测 OA 候选人，是"KGE+EHR 特征"范式的最新样本。
15. [Carvalho-2023] [**Knowledge Graph Embeddings for ICU readmission prediction**](https://doi.org/10.1186/s12911-022-02070-7). *BMC Med Inform Decis Mak*. 验证本体/KG 嵌入与临床表型联合用于 ICU 再入院预测的有效性。
16. [Yang-2025] [**Alzheimer's disease knowledge graph enhances knowledge discovery and disease prediction**](https://doi.org/10.1016/j.compbiomed.2025.110285). *Comput Biol Med*. 专病 KG + 嵌入用于 AD 风险预测，方法学路径与 ICKG 同构。
17. [Rjoob-2026] [**A multimodal vision knowledge graph of cardiovascular disease**](https://doi.org/10.1038/s44161-025-00757-4). *Nat Cardiovasc Res*. 将影像/临床/分子模态嵌入统一 KG 用于 CVD 风险预测，启示 ICKG 与影像/多组学联合。

---

## 主题 4 · 知识图谱链接预测与新知识发现（场景 1.4）

18. [Liu-2024] [**A probabilistic knowledge graph for target identification**](https://doi.org/10.1371/journal.pcbi.1011945). *PLOS Comput Biol*. 在 KG 上做概率推理识别免疫与肿瘤新靶点/新关联，链接预测的可迁移范式。
19. [Caufield-2023] [**KG-Hub: building and exchanging biological knowledge graphs**](https://doi.org/10.1093/bioinformatics/btad418). *Bioinformatics*. 可复用 KG 构建工具链与共享方案，覆盖 KG 构建-训练-发布全链路。

---

## 主题 5 · KG-RAG 在医学问答与健康报告解读中的应用（旗舰场景 3.1、1.2、2.2）

20. ⭐⭐ [Soman-2024] [**Biomedical knowledge graph-optimized prompt generation for large language models (KG-RAG with SPOKE)**](https://doi.org/10.1093/bioinformatics/btae560). *Bioinformatics*. 经典 KG-RAG 框架，KG-RAG 范式的奠基性工程。
21. ⭐⭐ [Liu-2025-JAMIA] [**Detecting emergencies in patient portal messages using LLMs and KG-based RAG**](https://doi.org/10.1093/jamia/ocaf059). *JAMIA*. 真实部署的 KG-RAG 提升临床消息分诊安全性，旗舰场景 3.1 的最强参考。
22. ⭐ [Hu-2025] [**A self-correcting Agentic Graph RAG for clinical decision support in hepatology**](https://doi.org/10.3389/fmed.2025.1716327). *Front Med*. 专科 KG-RAG + Agent 自校正最新样板。
23. [Su-2024-KGARevion] [**Knowledge Graph Based Agent for Complex, Knowledge-Intensive QA in Medicine (KGARevion)**](https://arxiv.org/abs/2410.04660). *arXiv*. Zitnik 团队的医学 KG-Agent，针对复杂、多跳医学问答显著优于普通 RAG。
24. [Kim-2026] [**MedSumGraph: enhancing GraphRAG for medical QA with summarization and optimized prompts**](https://doi.org/10.1016/j.artmed.2025.103311). *Artif Intell Med*. 针对医学问答优化的 GraphRAG 子图摘要与提示构造。
25. ⭐ [Gao-2025-Dx] [**Leveraging Medical Knowledge Graphs Into Large Language Models for Diagnosis Prediction**](https://doi.org/10.2196/58670). *JMIR AI*. KG-augmented LLM 在诊断辅助的方法学比较，本蓝图 2.2/3.1 的直接参考。

---

## 主题 6 · ICKG 差异化定位：对比对象与 KG×LLM 结合（定位 0.1–0.3）

26. ⭐⭐ [He-2026] [**AI-powered Immune Cell Knowledge Graph (ICKG) with granular immune contexts enables immune program interpretation**](https://doi.org/10.1038/s44387-025-00060-4). *npj Artif Intell*. **同名已发表 ICKG**（4 个细胞类型专用子图、仅 activation/inhibition 两类关系、基因集注释导向），本项目差异化定位的最直接对照与互补对象。
27. [Li-2026] [**A unified knowledge graph linking foodomics to chemical-disease networks and flavor profiles (FoodAtlas)**](https://doi.org/10.1038/s41538-025-00680-9). *npj Sci Food*. "LLM 抽取 + 逐边可溯源（provenance-tracked edges）"的跨域统一 KG 范式参照。
28. ⭐ [Peng-2024] [**Graph Retrieval-Augmented Generation: A Survey**](https://doi.org/10.1145/3777378). *ACM Trans Inf Syst*. GraphRAG 范式（图索引/图引导检索/图增强生成）系统综述，论证 KG 如何缓解 LLM 幻觉、时效与领域知识缺失。
29. [KG-Quality-2025] [**Improving Biomedical Knowledge Graph Quality: A Community Approach**](https://arxiv.org/abs/2508.21774). *arXiv*. KG 可信度社区评估标准（provenance、版本、更新频率、证据质量），证据可靠性框架的设计依据。

---

## 主题 7 · 证据可靠性分级（旗舰场景 3.1 深化）

30. ⭐⭐ [Guyatt-2008] [**GRADE: an emerging consensus on rating quality of evidence and strength of recommendations**](https://doi.org/10.1136/bmj.39489.470347.AD). *BMJ*. 临床证据分级金标准（高/中/低/极低四级），3.1 多维证据可靠性 A/B/C/D 分级的对齐基准。
31. [Schäfer-2024] [**BioKGrapher: Initial evaluation of automated knowledge graph construction from biomedical literature**](https://doi.org/10.1016/j.csbj.2024.10.017). *Comput Struct Biotechnol J*. 明确建议用文献计量学（研究阶段、证据等级、发表时效）对齐临床指南，证据维度设计的直接依据。

---

## 主题 8 · 免疫健康管理：免疫韧性与纵向追踪（场景 3.2/3.3/3.4）

32. ⭐⭐ [Ahuja-2023] [**Immune resilience despite inflammatory stress promotes longevity and favorable health outcomes including resistance to infection**](https://doi.org/10.1038/s41467-023-38238-6). *Nat Commun*. 提出可量化的免疫韧性（IR）指标，并证明其作为"免疫健康生物标志物"的价值。
33. ⭐ [Manoharan-2025] [**The 15-Year Survival Advantage: Immune Resilience as a Salutogenic Force in Healthy Aging**](https://doi.org/10.1111/acel.70063). *Aging Cell*. 以 TCF7 为核心的 IR 对抗炎性衰老/免疫衰老/细胞衰老，增强疫苗应答，中年是干预关键窗口。

---

## 项目相关核心论文

34. ⭐ [Zhou-2026-LCKG] [**Fine-tuned large language models with structured prompts enable efficient construction of lung cancer knowledge graphs**](https://doi.org/10.1038/s41746-025-02232-y). *npj Digit Med*. 本 ICKG 项目所参考的核心方法学论文，LCKG 范式的奠基。

---

## "先读 7 篇"推荐阅读顺序

| 顺序 | 文献 | 为什么先读 |
|---|---|---|
| 1 | [He-2026 ICKG](https://doi.org/10.1038/s44387-025-00060-4) | 看清同名工作边界，理解本项目差异化定位 |
| 2 | [Gao-2025 MDKG](https://doi.org/10.1038/s41467-025-62781-z) | 完整看一遍 KG+临床预测范式 |
| 3 | [Zhou-2026 LCKG](https://doi.org/10.1038/s41746-025-02232-y) | 看 ICKG 自身工程范式 |
| 4 | [Zhao-2023 KG-GNN ICI](https://doi.org/10.1093/bib/bbad023) | 旗舰场景 2.3 的方法母本 |
| 5 | [Soman-2024 SPOKE-KG-RAG](https://doi.org/10.1093/bioinformatics/btae560) | KG-RAG 必备背景 |
| 6 | [Chandak-2023 PrimeKG](https://doi.org/10.1038/s41597-023-01960-3) | 看精准医学 KG 工业级数据底座 |
| 7 | [Guyatt-2008 GRADE](https://doi.org/10.1136/bmj.39489.470347.AD) | 旗舰场景 3.1 证据分级的基准 |

---

## 引用约定

- DOI → `https://doi.org/<DOI>`
- PMID → `https://pubmed.ncbi.nlm.nih.gov/<PMID>/`
- arXiv → `https://arxiv.org/abs/<arxiv_id>`
- 仅在 DOI 不可得或论文尚未被 Crossref 收录时退而使用 PMID/arXiv 链接

miao!
