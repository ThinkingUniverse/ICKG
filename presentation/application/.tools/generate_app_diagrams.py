#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
generate_app_diagrams.py
========================
Batch generator for ICKG application-scenario Excalidraw diagrams.
为 ICKG 各应用场景批量生成 Excalidraw 流程图（PPT 尺寸 1600×900）。

每个 .md 同目录会生成一份 .excalidraw 文件，统一布局：
顶部 标题 + 副标题 → 三栏 输入 / 处理 / 输出 → 底部 参考文献。
字体 Normal (fontFamily=6)，最小字号 L=28（标题 XL=36）。
"""

import argparse
import json
import sys
from pathlib import Path

# ===================== 视觉常量 =====================
FF_NORMAL, FS_L, FS_XL = 6, 28, 36
C_INPUT_BG, C_INPUT_STROKE   = "#e7f5ff", "#1971c2"
C_PROC_BG,  C_PROC_STROKE    = "#d3f9d8", "#2f9e44"
C_OUTPUT_BG, C_OUTPUT_STROKE = "#fff9db", "#e8590c"
C_REF_BG,   C_REF_STROKE     = "#f1f3f5", "#495057"
C_WHITE, C_TEXT, C_SUB       = "#ffffff", "#1e1e1e", "#495057"
T_STAMP = 1779370000000


def _base(eid):
    """通用 Excalidraw element 字段。"""
    h = abs(hash(eid))
    return {
        "id": eid, "angle": 0,
        "fillStyle": "solid", "strokeStyle": "solid",
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None,
        "seed": h % 999983, "version": 1,
        "versionNonce": (h * 31) % 999983,
        "isDeleted": False, "updated": T_STAMP,
        "link": None, "locked": False,
    }


def text_el(eid, x, y, w, h, text, *, size=FS_L, color=C_TEXT,
            align="center", valign="middle", container=None, index="a0"):
    """构造 text 元素（独立或绑定到容器）。"""
    e = _base(eid); e.update({
        "type": "text", "x": x, "y": y, "width": w, "height": h,
        "strokeColor": color, "backgroundColor": "transparent",
        "strokeWidth": 1, "index": index, "roundness": None,
        "boundElements": [], "text": text, "fontSize": size,
        "fontFamily": FF_NORMAL, "textAlign": align,
        "verticalAlign": valign, "baseline": size - 2,
        "containerId": container, "originalText": text,
        "lineHeight": 1.25, "autoResize": True,
    })
    return e


def rect_el(eid, x, y, w, h, *, bg, stroke, sw=2, dashed=False,
            bound=None, index="a0"):
    """构造 rectangle 元素。"""
    e = _base(eid); e.update({
        "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke, "backgroundColor": bg,
        "strokeWidth": sw,
        "strokeStyle": "dashed" if dashed else "solid",
        "index": index, "roundness": {"type": 3},
        "boundElements": bound or [],
    })
    return e


def arrow_el(eid, x, y, dx, dy, *, stroke=C_TEXT, sw=2,
             start_id=None, end_id=None, index="a0"):
    """构造箭头元素（支持绑定起止端点到形状）。"""
    e = _base(eid); e.update({
        "type": "arrow", "x": x, "y": y,
        "width": abs(dx) if dx else 0, "height": abs(dy) if dy else 0,
        "strokeColor": stroke, "backgroundColor": "transparent",
        "strokeWidth": sw, "index": index, "roundness": {"type": 2},
        "boundElements": [], "points": [[0, 0], [dx, dy]],
        "startBinding": ({"elementId": start_id, "focus": 0, "gap": 1}
                         if start_id else None),
        "endBinding": ({"elementId": end_id, "focus": 0, "gap": 1}
                       if end_id else None),
        "lastCommittedPoint": None,
        "startArrowhead": None, "endArrowhead": "arrow",
    })
    return e


def build(sc):
    """根据场景数据组装完整 Excalidraw JSON。

    注意：Excalidraw 5.0+ 使用 fractional indexing，
    要求 elements 数组顺序与 index 字段字母序严格一致，
    否则文件会被判定为 invalid file。
    本函数用统一计数器派发 index，自然保持升序。
    """
    els = []
    counter = [0]

    def nx():
        """派发下一个字母序递增的 index（a000, a001, ...）。"""
        c = counter[0]
        counter[0] += 1
        return f"a{c:03d}"

    # 顶部 标题 + 副标题
    els.append(text_el("main-title", 200, 25, 1200, 50, sc["title"],
                       size=FS_XL, index=nx()))
    els.append(text_el("subtitle", 100, 90, 1400, 40, sc["subtitle"],
                       color=C_SUB, index=nx()))
    # 三栏标题
    els.append(text_el("label-input",  60, 150, 460, 40, "📋 输入",
                       color=C_INPUT_STROKE, index=nx()))
    els.append(text_el("label-process", 570, 150, 460, 40, "⚙️ 处理流程",
                       color=C_PROC_STROKE, index=nx()))
    els.append(text_el("label-output", 1080, 150, 460, 40, "📄 输出",
                       color=C_OUTPUT_STROKE, index=nx()))

    # 输入大框（虚线） + 3 个 item 卡片
    els.append(rect_el("input-bg", 40, 200, 500, 510, bg=C_INPUT_BG,
                       stroke=C_INPUT_STROKE, dashed=True,
                       bound=[{"type": "arrow", "id": "arrow-in-to-proc"}],
                       index=nx()))
    for i, it in enumerate(sc["input_items"]):
        y = 230 + i * 160
        rid, tid = f"item-{i+1}", f"item-{i+1}-text"
        els.append(rect_el(rid, 70, y, 440, 130, bg=C_WHITE,
                           stroke=C_INPUT_STROKE,
                           bound=[{"type": "text", "id": tid}],
                           index=nx()))
        els.append(text_el(tid, 90, y + 20, 400, 90, it,
                           container=rid, index=nx()))

    # 处理流程 3 个 Step + 两个垂直箭头
    for i, st in enumerate(sc["process_steps"]):
        y = 220 + i * 175
        rid, tid = f"step-{i+1}", f"step-{i+1}-text"
        bound = [{"type": "text", "id": tid}]
        if i == 0:
            bound.append({"type": "arrow", "id": "arrow-in-to-proc"})
        if i > 0:
            bound.append({"type": "arrow",
                          "id": f"arrow-step-{i}-{i+1}"})
        if i < 2:
            bound.append({"type": "arrow",
                          "id": f"arrow-step-{i+1}-{i+2}"})
        if i == 2:
            bound.append({"type": "arrow", "id": "arrow-proc-to-out"})
        els.append(rect_el(rid, 560, y, 480, 130, bg=C_PROC_BG,
                           stroke=C_PROC_STROKE, sw=3, bound=bound,
                           index=nx()))
        els.append(text_el(tid, 580, y + 20, 440, 90, st,
                           container=rid, index=nx()))
        if i < 2:
            els.append(arrow_el(f"arrow-step-{i+1}-{i+2}", 800, y + 135,
                                0, 35, stroke=C_PROC_STROKE, sw=3,
                                start_id=f"step-{i+1}",
                                end_id=f"step-{i+2}", index=nx()))

    # 输出大框（虚线） + 多行文本
    els.append(rect_el("output-bg", 1060, 200, 500, 510, bg=C_OUTPUT_BG,
                       stroke=C_OUTPUT_STROKE, dashed=True,
                       bound=[{"type": "arrow", "id": "arrow-proc-to-out"}],
                       index=nx()))
    els.append(text_el("output-text", 1080, 220, 460, 470, sc["output"],
                       valign="top", index=nx()))

    # 横向大箭头：输入→处理 / 处理→输出
    els.append(arrow_el("arrow-in-to-proc", 542, 455, 18, 0,
                        stroke=C_REF_STROKE, sw=4,
                        start_id="input-bg", end_id="step-2",
                        index=nx()))
    els.append(arrow_el("arrow-proc-to-out", 1042, 455, 18, 0,
                        stroke=C_REF_STROKE, sw=4,
                        start_id="step-3", end_id="output-bg",
                        index=nx()))

    # 底部参考文献框（多行，灰色虚线）
    els.append(rect_el("refs-box", 40, 730, 1520, 150, bg=C_REF_BG,
                       stroke=C_REF_STROKE, dashed=True, sw=2,
                       bound=[{"type": "text", "id": "refs-text"}],
                       index=nx()))
    els.append(text_el("refs-text", 60, 745, 1480, 120,
                       "📚 参考文献\n" + sc["refs"],
                       container="refs-box", index=nx()))

    return {
        "type": "excalidraw", "version": 2,
        "source": "https://excalidraw.com",
        "elements": els,
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
        "files": {},
    }


# ===================== 10 个应用场景数据 =====================
SCENARIOS = [
    {
        "path": "01_knowledge_applications/1.1_retrieval_and_qa",
        "title": "ICKG 知识检索与图谱问答",
        "subtitle": "自然语言/Cypher  →  Neo4j 图查询  →  排序结果 + PMID 回链",
        "input_items": [
            "自然语言查询\n\"与 CD8+ T 相关的疾病\"",
            "实体节点\nCD8+ T cell",
            "关系过滤（可选）\nASSOCIATED_WITH",
        ],
        "process_steps": [
            "Step 1\n实体识别 & Cypher 翻译",
            "Step 2\nNeo4j 图数据库执行",
            "Step 3\n按证据数排序 + 回链",
        ],
        "output": ("Top 5 关联疾病：\n\n"
                   "· melanoma  (1247 篇)\n"
                   "· NSCLC  (982 篇)\n"
                   "· HBV 感染  (537 篇)\n"
                   "· HIV 感染  (481 篇)\n"
                   "· RA  (412 篇)\n\n"
                   "每行附 PMID 可点击\n核验文献来源"),
        "refs": ("· Zhou et al., npj Digital Medicine, 2026\n"
                 "· Atallah et al., BMC Bioinformatics, 2020\n"
                 "· Shao et al., Briefings in Bioinformatics, 2021"),
    },
    {
        "path": "01_knowledge_applications/1.2_kg_rag",
        "title": "ICKG KG-RAG 增强问答",
        "subtitle": "用户问题  →  子图抽取 + 提示构造  →  LLM 受控生成 + 引用",
        "input_items": [
            "用户问题\n\"PD-L1 如何抑制\nCD8+ T 细胞功能？\"",
            "目标实体\nPD-L1, CD8+ T cell",
            "上下文设定\n肿瘤微环境",
        ],
        "process_steps": [
            "Step 1\n实体链接 + 子图抽取",
            "Step 2\n子图序列化 + 提示构造",
            "Step 3\nLLM 生成 + 引用绑定",
        ],
        "output": ("PD-L1 与 PD-1 结合\n抑制 TCR 信号通路\n[PMID: 18173375]\n\n"
                   "降低 IFN-γ 分泌、\n细胞毒性受损\n[PMID: 26193342]\n\n"
                   "这是 anti-PD-1\n单抗的核心机制\n[PMID: 28525752]"),
        "refs": ("· Soman et al., Bioinformatics, 2024\n"
                 "· Kim et al., Artificial Intelligence in Medicine, 2026\n"
                 "· Su et al., arXiv (KGARevion), 2024"),
    },
    {
        "path": "01_knowledge_applications/1.3_causal_discovery",
        "title": "ICKG 因果发现与多跳推理",
        "subtitle": "起止节点  →  有向路径搜索 + 打分  →  因果链 + 自然语言叙事",
        "input_items": [
            "起点节点\nIL-6  (cytokine)",
            "终点节点\nrheumatoid arthritis",
            "搜索约束\n最多 3-hop，有向",
        ],
        "process_steps": [
            "Step 1\nCypher 多跳路径搜索",
            "Step 2\n路径打分（频次 × 衰减）",
            "Step 3\nLLM 改写为因果叙事",
        ],
        "output": ("Top-3 因果链：\n\n"
                   "①  IL-6  →  Th17  →  RA\n"
                   "    PROMOTES → PROMOTES\n"
                   "    score = 18.7\n\n"
                   "②  IL-6  →  STAT3  →\n"
                   "    osteoclast  →  RA\n\n"
                   "③  IL-6  →  B cell  →\n"
                   "    自身抗体  →  RA"),
        "refs": ("· Gao et al., Nature Communications, 2025\n"
                 "· Cui et al., Nature (Immune Dictionary), 2024\n"
                 "· Olbei et al., Cells (CytokineLink), 2021"),
    },
    {
        "path": "01_knowledge_applications/1.4_new_knowledge_generation",
        "title": "ICKG 链接预测与新知识生成",
        "subtitle": "(head, relation, ?)  →  KGE 模型打分  →  Top-K 新候选 + 验证",
        "input_items": [
            "头实体 head\nPD-1+ TIM-3+ CD8 T",
            "关系类型 relation\nASSOCIATED_WITH",
            "返回数量 K\nK = 5",
        ],
        "process_steps": [
            "Step 1\n训练 KGE 模型（ComplEx）",
            "Step 2\n对所有尾实体打分",
            "Step 3\n过滤已知 + Top-K 排序",
        ],
        "output": ("Top-5 候选尾实体：\n\n"
                   "1.  HCC  (肝细胞癌)\n     0.842   ✦ 新假设\n\n"
                   "2.  CLL  (慢性淋白)\n     0.811   ✦ 新假设\n\n"
                   "3.  tuberculosis  已知\n\n"
                   "4.  HCV 感染  已知\n\n"
                   "5.  食管 SCC\n     0.762   ✦ 新假设"),
        "refs": ("· Liu et al., PLOS Computational Biology, 2024\n"
                 "· Chandak et al., Scientific Data (PrimeKG), 2023\n"
                 "· Caufield et al., Bioinformatics (KG-Hub), 2023"),
    },
    {
        "path": "02_clinical_applications/2.1_prevention",
        "title": "ICKG 免疫疾病早期风险预测",
        "subtitle": "患者 EHR + ICKG embedding  →  XGBoost  →  5 年风险概率 + SHAP",
        "input_items": [
            "人口学 + 生活方式\nage=42, F, BMI=24\n吸烟=否",
            "既往疾病 (PheCodes)\n['250.1','244.4','714.0']\n(T1D · 甲减 · RA)",
            "家族史\n自身免疫病阳性",
        ],
        "process_steps": [
            "Step 1\n实体 → ICD-10 → PheCode",
            "Step 2\nKG 向量 + 基线特征拼接",
            "Step 3\nXGBoost + SHAP 解释",
        ],
        "output": ("5 年 IBD 风险预测：\n\n"
                   "概率 = 0.187\n队列排名 = top 4.3%\n\n"
                   "关键 SHAP 贡献：\n"
                   "· kg_vec[37] (Treg) ↑\n"
                   "· 家族史阳性\n"
                   "· 244.4 甲减 ↑\n\n"
                   "AUC = 0.82\n(EHR-only = 0.71)"),
        "refs": ("· Gao et al., Nature Communications (MDKG), 2025\n"
                 "· Wang et al., npj Digital Medicine, 2026\n"
                 "· Yang et al., Computers in Biology and Medicine, 2025"),
    },
    {
        "path": "02_clinical_applications/2.2_diagnosis",
        "title": "ICKG 免疫相关疾病辅助诊断",
        "subtitle": "症状/检验/影像  →  help_identify 反向查询  →  鉴别诊断报告",
        "input_items": [
            "症状\n多关节炎 + 晨僵 >1h",
            "检验\n抗 CCP+, RF+,\nCRP 38 mg/L",
            "影像\n双手关节侵蚀",
        ],
        "process_steps": [
            "Step 1\n实体识别 → KG 节点链接",
            "Step 2\nhelp_identify 反向查询",
            "Step 3\nLLM 生成鉴别诊断报告",
        ],
        "output": ("鉴别诊断（按可能性）：\n\n"
                   "①  类风湿关节炎 RA\n"
                   "    抗 CCP+ 满足 ACR\n"
                   "    /EULAR 2010 标准\n\n"
                   "②  银屑病关节炎\n"
                   "    需查皮肤 / HLA-B27\n\n"
                   "③  SLE 合并关节炎\n"
                   "    需查 ANA / dsDNA\n\n"
                   "建议：DAS28 评分"),
        "refs": ("· Gao et al., JMIR AI, 2025\n"
                 "· Hu et al., Frontiers in Medicine, 2025\n"
                 "· Su et al., arXiv (KGARevion), 2024"),
    },
    {
        "path": "02_clinical_applications/2.3_treatment",
        "title": "ICKG 引导 GNN 预测 ICI 响应",
        "subtitle": "肿瘤组学 + ICKG 子图  →  HeteroGNN  →  响应概率 + 可解释路径",
        "input_items": [
            "转录组 + 突变\nCD8A=6.8, GZMB=7.2\nIFNG=5.4, PDCD1=6.1",
            "标志物\nTMB=18.7, MSS,\nPD-L1 TPS=35%",
            "肿瘤亚型\ncutaneous melanoma",
        ],
        "process_steps": [
            "Step 1\n构造患者异构图",
            "Step 2\nKG 引导 HeteroGNN",
            "Step 3\n响应概率 + 路径解释",
        ],
        "output": ("ICI 响应预测：\n\n"
                   "prob = 0.78\n标签 = responder\n置信度 = 高\n\n"
                   "关键支持路径：\n"
                   "· CD8+ T → INHIBITS\n  → melanoma\n"
                   "· high TMB → 新抗原\n  → T cell priming\n\n"
                   "推荐：Pembrolizumab\n单药"),
        "refs": ("· Zhao et al., Briefings in Bioinformatics, 2023\n"
                 "· Jiang et al., Journal of Advanced Research (IRnet), 2024\n"
                 "· Liu et al., Briefings in Bioinformatics (CKG-TPI), 2025"),
    },
    {
        "path": "02_clinical_applications/2.4_prognosis",
        "title": "ICKG + DeepSurv 生存预测",
        "subtitle": "临床基线 + ICKG embedding  →  DeepSurv  →  风险分层 + 生存曲线",
        "input_items": [
            "临床基线\nage=61, stage=IIIB,\nBRAF V600E+",
            "病理 / 免疫\ntumor purity=0.72,\nTIL high",
            "治疗\nanti-PD-1 单药",
        ],
        "process_steps": [
            "Step 1\n抽取 ICKG embedding",
            "Step 2\n特征拼接 → DeepSurv",
            "Step 3\n风险分层 + 校准",
        ],
        "output": ("预后预测：\n\n"
                   "risk_score = 0.28\n分层 = 低风险\n"
                   "24m OS = 0.86\n60m OS = 0.71\n\n"
                   "模型 C-index：\n"
                   "· Cox (clin)  = 0.65\n"
                   "· DeepSurv (clin) = 0.69\n"
                   "· DeepSurv + KG = 0.74"),
        "refs": ("· Ye et al., BMC Cancer, 2025\n"
                 "· Rjoob et al., Nature Cardiovascular Research, 2026\n"
                 "· Gao et al., Nature Communications, 2025"),
    },
    {
        "path": "03_other_applications/3.1_drug_repurposing",
        "title": "ICKG 药物发现与重定位",
        "subtitle": "目标疾病  →  KG 路径推理 + KGE 链接预测  →  Top-K 候选药物",
        "input_items": [
            "目标疾病\nSLE\n(系统性红斑狼疮)",
            "候选池 + 链接\nDrugBank / ChEMBL\n约 3000 上市药",
            "约束\nNOT TREATMENT_FOR\n(排除已知)",
        ],
        "process_steps": [
            "Step 1\n构造 drug→target→cell→disease",
            "Step 2\n路径打分 + KGE 排序",
            "Step 3\n过滤已知 + Top-K 输出",
        ],
        "output": ("Top-5 重定位候选：\n\n"
                   "1. Baricitinib (RA)\n   JAK→IFN-α→pDC ★\n\n"
                   "2. Belimumab\n   已批准 (校验)\n\n"
                   "3. Anifrolumab\n   已批准 (校验)\n\n"
                   "4. Tofacitinib (RA)\n\n"
                   "5. Daratumumab\n   ✦ 新假设"),
        "refs": ("· Richardson et al., Translational Neurodegeneration, 2023\n"
                 "· Liu et al., PLOS Computational Biology, 2024\n"
                 "· Koutsandreas et al., Annual Review of Biomedical Data Science, 2025"),
    },
    {
        "path": "03_other_applications/3.3_education_and_research",
        "title": "ICKG 教育、患教与科研协作",
        "subtitle": "问题 / 主题  →  分流 + KG 查询  →  科普 / 研究空白 / 综述大纲",
        "input_items": [
            "A. 患教问题\n\"IgG4 升高是什么？\"",
            "B. 研究探索\n白点分析\n(Treg, 2-hop)",
            "C. 综述主题\n\"CAR-T 实体瘤障碍\"",
        ],
        "process_steps": [
            "Step 1\n问题分流 + 模式匹配",
            "Step 2\nICKG 子图 / 社区检测",
            "Step 3\nLLM 包装为对应输出",
        ],
        "output": ("三类输出：\n\n"
                   "A. 患教 → 200 字科普\n   + 强制转诊提示\n\n"
                   "B. 白点列表（节选）\n"
                   "   · 子宫内膜异位症\n"
                   "   · COPD\n"
                   "   · 自闭症谱系\n\n"
                   "C. 综述大纲\n"
                   "   1. 引言\n"
                   "   2. 抗原与毒性\n"
                   "   3. TME 抑制网络\n   …"),
        "refs": ("· Zhou et al., npj Digital Medicine (LCKG), 2026\n"
                 "· Cui et al., Nature (Immune Dictionary), 2024\n"
                 "· Caufield et al., Bioinformatics (KG-Hub), 2023"),
    },
]


def main():
    p = argparse.ArgumentParser(
        description="批量生成 ICKG 应用场景的 Excalidraw 流程图")
    p.add_argument("--output-root", "-o", type=Path, required=True,
                   help="输出根目录（通常为 report/application）")
    p.add_argument("--scenarios", "-s", nargs="*", default=None,
                   help="只生成指定 path 的场景；不指定则生成全部 10 个")
    args = p.parse_args()

    targets = (SCENARIOS if not args.scenarios
               else [s for s in SCENARIOS if s["path"] in args.scenarios])
    if not targets:
        avail = "\n  ".join(s["path"] for s in SCENARIOS)
        print(f"[ERR] 未匹配到任何场景。可选场景:\n  {avail}",
              file=sys.stderr)
        sys.exit(1)

    for sc in targets:
        out = args.output_root / (sc["path"] + ".excalidraw")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(build(sc), ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"[OK] 生成 → {out}")

    print(f"\n共生成 {len(targets)} 个 Excalidraw 文件")


if __name__ == "__main__":
    main()
