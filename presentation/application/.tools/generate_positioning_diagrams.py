#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
generate_positioning_diagrams.py
================================
Generate the three ICKG positioning (差异化定位) Excalidraw diagrams.
为 ICKG 三篇差异化定位（0.1/0.2/0.3）生成 Excalidraw 对比图（PPT 1600×900）。

复用与 generate_app_diagrams.py 一致的健壮做法：
统一顺序 index 计数器（保证 elements 与 index 字典序一致）+ bound-text 绑定文本。
字体 Normal(fontFamily=6)。生成四张图：
  0.1 vs 其他知识图谱（四栏对比）
  0.2 vs 大模型（互补双栏）
  0.3 与大模型结合（架构图）
  0.4 vs He-2026 同名 ICKG（三问三栏深度对比）
"""

import argparse
import json
from pathlib import Path

# ===================== 视觉常量 =====================
FF = 6                       # Normal 字体
C_TITLE, C_SUB, C_TEXT = "#1e1e1e", "#495057", "#1e1e1e"
C_WHITE = "#ffffff"
# 配色
BLUE_BG, BLUE_ST = "#e7f5ff", "#1971c2"
GRAY_BG, GRAY_ST = "#f1f3f5", "#495057"
GREEN_BG, GREEN_ST = "#d3f9d8", "#2f9e44"
ORANGE_BG, ORANGE_ST = "#fff9db", "#e8590c"
GOLD_BG, GOLD_ST = "#fff3bf", "#f08c00"      # 高亮（本项目 ICKG）
RED_BG, RED_ST = "#ffc9c9", "#e03131"
T_STAMP = 1779370000000


def _base(eid):
    h = abs(hash(eid))
    return {
        "id": eid, "angle": 0, "fillStyle": "solid", "strokeStyle": "solid",
        "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
        "seed": h % 999983, "version": 1, "versionNonce": (h * 31) % 999983,
        "isDeleted": False, "updated": T_STAMP, "link": None, "locked": False,
    }


class Canvas:
    """带顺序 index 的元素收集器，保证 elements 顺序 == index 字典序。"""

    def __init__(self):
        self.els = []
        self._c = 0

    def _nx(self):
        i = f"a{self._c:03d}"
        self._c += 1
        return i

    def text(self, eid, x, y, w, h, text, *, size=20, color=C_TEXT,
             align="center", valign="middle", container=None):
        e = _base(eid)
        e.update({
            "type": "text", "x": x, "y": y, "width": w, "height": h,
            "strokeColor": color, "backgroundColor": "transparent",
            "strokeWidth": 1, "index": self._nx(), "roundness": None,
            "boundElements": [], "text": text, "fontSize": size,
            "fontFamily": FF, "textAlign": align, "verticalAlign": valign,
            "baseline": size - 2, "containerId": container,
            "originalText": text, "lineHeight": 1.25, "autoResize": True,
        })
        self.els.append(e)
        return e

    def rect(self, eid, x, y, w, h, *, bg, st, sw=2, text=None, tsize=20,
             tcolor=C_TEXT, dashed=False, arrows=None):
        bound = []
        if text is not None:
            bound.append({"type": "text", "id": eid + "-t"})
        for aid in (arrows or []):
            bound.append({"type": "arrow", "id": aid})
        e = _base(eid)
        e.update({
            "type": "rectangle", "x": x, "y": y, "width": w, "height": h,
            "strokeColor": st, "backgroundColor": bg, "strokeWidth": sw,
            "strokeStyle": "dashed" if dashed else "solid",
            "index": self._nx(), "roundness": {"type": 3}, "boundElements": bound,
        })
        self.els.append(e)
        if text is not None:
            self.text(eid + "-t", x + 14, y + 12, w - 28, h - 24, text,
                      size=tsize, color=tcolor, valign="middle", container=eid)
        return e

    def ellipse(self, eid, x, y, w, h, *, bg, st, sw=2, text=None, tsize=24,
                tcolor=C_TEXT, arrows=None):
        bound = []
        if text is not None:
            bound.append({"type": "text", "id": eid + "-t"})
        for aid in (arrows or []):
            bound.append({"type": "arrow", "id": aid})
        e = _base(eid)
        e.update({
            "type": "ellipse", "x": x, "y": y, "width": w, "height": h,
            "strokeColor": st, "backgroundColor": bg, "strokeWidth": sw,
            "index": self._nx(), "roundness": None, "boundElements": bound,
        })
        self.els.append(e)
        if text is not None:
            self.text(eid + "-t", x + 14, y + 12, w - 28, h - 24, text,
                      size=tsize, color=tcolor, valign="middle", container=eid)
        return e

    def arrow(self, eid, x, y, dx, dy, *, st=GRAY_ST, sw=3,
              start_id=None, end_id=None, both=False):
        e = _base(eid)
        e.update({
            "type": "arrow", "x": x, "y": y,
            "width": abs(dx), "height": abs(dy),
            "strokeColor": st, "backgroundColor": "transparent",
            "strokeWidth": sw, "index": self._nx(), "roundness": {"type": 2},
            "boundElements": [], "points": [[0, 0], [dx, dy]],
            "startBinding": ({"elementId": start_id, "focus": 0, "gap": 2}
                             if start_id else None),
            "endBinding": ({"elementId": end_id, "focus": 0, "gap": 2}
                           if end_id else None),
            "lastCommittedPoint": None,
            "startArrowhead": "arrow" if both else None,
            "endArrowhead": "arrow",
        })
        self.els.append(e)
        return e

    def dump(self):
        return {
            "type": "excalidraw", "version": 2,
            "source": "https://excalidraw.com",
            "elements": self.els,
            "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
            "files": {},
        }


# ===================== 0.1 vs 其他知识图谱 =====================
def build_0_1():
    c = Canvas()
    c.text("t", 100, 28, 1400, 50,
           "ICKG vs 其他知识图谱：差异化定位", size=36, color=C_TITLE)
    c.text("st", 100, 86, 1400, 36,
           "唯一打通『免疫机制层（细胞·因子·通路）→ 临床动作层（疾病·诊断·干预）』的免疫专用图谱",
           size=22, color=C_SUB)
    cols = [
        ("c1", 60, GRAY_BG, GRAY_ST, "手工策划免疫库",
         "ImmunoGlobe / CellTalkDB\nSpaTalk / CytokineLink\n\n· 人工策划，规模小\n· 多为单一相互作用\n· 静态、更新慢\n· 缺临床可执行层"),
        ("c2", 440, BLUE_BG, BLUE_ST, "通用生物医学大图",
         "PrimeKG / SPOKE / iBKH\n\n· 广而浅\n· 免疫粒度不足\n· 关系多无向/弱语义\n· 难支撑有向因果推理"),
        ("c3", 820, ORANGE_BG, ORANGE_ST, "He-2026 ICKG（同名）",
         "npj Artif Intell 2026\n\n· 4 个细胞类型子图\n· 仅 2 类关系\n  (activation/inhibition)\n· 基因集注释导向\n· 明确不做临床"),
        ("c4", 1200, GOLD_BG, GOLD_ST, "★ 本项目 ICKG",
         "· 423,823 三元组\n· 235,457 实体 / 19 类\n· 89 类关系（含\n  treatment_for 等）\n· 含疾病/干预/化学\n· 逐边可溯源 PMID\n· 机制→临床全闭环"),
    ]
    for cid, x, bg, st, head, body in cols:
        sw = 4 if cid == "c4" else 2
        c.rect(cid + "h", x, 145, 340, 64, bg=bg, st=st, sw=sw,
               text=head, tsize=24, tcolor=st)
        c.rect(cid + "b", x, 220, 340, 470, bg=C_WHITE, st=st, sw=sw,
               text=body, tsize=20, tcolor=C_TEXT)
    c.rect("concl", 60, 715, 1480, 150, bg=GREEN_BG, st=GREEN_ST, sw=3,
           dashed=True,
           text=("解决的特定问题：把碎片化、不可计算的免疫学文献，变成\n"
                 "可结构化检索 · 可多跳因果推理 · 可预测新关联 · 临床可执行 · 全程可溯源 的知识底座。"),
           tsize=24, tcolor=GREEN_ST)
    return c.dump()


# ===================== 0.2 vs 大模型 =====================
def build_0_2():
    c = Canvas()
    c.text("t", 100, 28, 1400, 50,
           "ICKG 会被大模型淘汰吗？—— 不会，二者互补", size=36, color=C_TITLE)
    c.text("st", 100, 86, 1400, 36,
           "大模型越强，越需要『可溯源 · 可审计 · 可更新』的事实底座", size=22, color=C_SUB)
    # 左：大模型
    c.rect("llm", 80, 170, 600, 430, bg=BLUE_BG, st=BLUE_ST, sw=3,
           text=("大模型 LLM（GPT/Claude/Gemini）\n"
                 "“会说话的大脑”\n\n"
                 "强：自然语言理解与生成\n　　常识 / 改写 / 跨任务泛化\n\n"
                 "弱：✗ 幻觉、不可问责\n　　✗ 不可逐句溯源\n　　✗ 知识固化、时效黑箱"),
           tsize=22, tcolor=BLUE_ST, arrows=["a-l2c"])
    # 右：ICKG
    c.rect("kg", 920, 170, 600, 430, bg=GOLD_BG, st=GOLD_ST, sw=4,
           text=("ICKG 知识图谱\n"
                 "“带脚注的记忆 / 事实锚”\n\n"
                 "强：✓ 逐边可溯源 PMID\n　　✓ 有向因果 / 多跳路径\n"
                 "　　✓ 确定性 / 可审计 / 可更新\n　　✓ 多维证据分级\n\n"
                 "弱：不会“说人话”汇总（交给 LLM）"),
           tsize=22, tcolor=GOLD_ST, arrows=["a-c2r"])
    # 中间互补双箭头
    c.rect("comp", 700, 350, 200, 70, bg=GREEN_BG, st=GREEN_ST, sw=3,
           text="互补", tsize=28, tcolor=GREEN_ST,
           arrows=["a-l2c", "a-c2r"])
    c.arrow("a-l2c", 682, 385, 16, 0, st=GREEN_ST, start_id="llm",
            end_id="comp", both=True)
    c.arrow("a-c2r", 902, 385, 16, 0, st=GREEN_ST, start_id="comp",
            end_id="kg", both=True)
    c.rect("concl", 80, 715, 1440, 150, bg=ORANGE_BG, st=ORANGE_ST, sw=3,
           dashed=True,
           text=("结论：ICKG 不是大模型的过时替代品，而是大模型时代愈发刚需的『事实锚』——\n"
                 "判断知识资产会不会被淘汰，要看它提供的是可被参数记忆替代的泛知识，还是参数给不了的可溯源、可审计、可更新的结构化事实。"),
           tsize=22, tcolor=ORANGE_ST)
    return c.dump()


# ===================== 0.3 与大模型结合 =====================
def build_0_3():
    c = Canvas()
    c.text("t", 100, 28, 1400, 50,
           "ICKG × 最先进大模型：如何结合", size=36, color=C_TITLE)
    c.text("st", 100, 86, 1400, 36,
           "大模型负责『语言与推理』，ICKG 负责『事实与证据』", size=22, color=C_SUB)
    # 顶部输入
    c.rect("q", 580, 150, 440, 70, bg=GRAY_BG, st=GRAY_ST, sw=2,
           text="用户问题 / 临床输入", tsize=24, tcolor=GRAY_ST,
           arrows=["a-q-llm", "a-q-kg"])
    # 两条泳道
    c.rect("llm", 120, 300, 560, 150, bg=BLUE_BG, st=BLUE_ST, sw=3,
           text=("大模型（GPT / Claude / Gemini）\n语言理解 · 规划 · 生成 · 改写"),
           tsize=22, tcolor=BLUE_ST, arrows=["a-q-llm", "a-llm-kg", "a-llm-out"])
    c.rect("kg", 920, 300, 560, 150, bg=GOLD_BG, st=GOLD_ST, sw=4,
           text=("ICKG（事实与证据）\n子图检索 · 有向因果 · PMID · 证据分级"),
           tsize=22, tcolor=GOLD_ST, arrows=["a-q-kg", "a-llm-kg", "a-kg-out"])
    c.arrow("a-q-llm", 600, 222, -180, 76, st=GRAY_ST, start_id="q", end_id="llm")
    c.arrow("a-q-kg", 1000, 222, 180, 76, st=GRAY_ST, start_id="q", end_id="kg")
    c.arrow("a-llm-kg", 682, 375, 236, 0, st=GREEN_ST, start_id="llm",
            end_id="kg", both=True)
    # 中间标注
    c.text("mid", 700, 340, 200, 30, "检索 / 约束 / 核验", size=18, color=GREEN_ST)
    # 四种范式
    c.rect("para", 120, 500, 1360, 90, bg="#f8f0fc", st="#9c36b5", sw=2,
           text=("结合范式（由浅入深）：  KG-RAG  →  GraphRAG  →  Agentic Graph-RAG  →  KG 作事实校验器"),
           tsize=22, tcolor="#9c36b5")
    # 底部输出
    c.rect("out", 430, 660, 740, 90, bg=GREEN_BG, st=GREEN_ST, sw=3,
           text="回答 + PMID 引用 + 证据等级（A/B/C/D）", tsize=24, tcolor=GREEN_ST,
           arrows=["a-llm-out", "a-kg-out"])
    c.arrow("a-llm-out", 400, 452, 180, 208, st=BLUE_ST, start_id="llm", end_id="out")
    c.arrow("a-kg-out", 1200, 452, -180, 208, st=GOLD_ST, start_id="kg", end_id="out")
    c.rect("solve", 120, 775, 1360, 90, bg=ORANGE_BG, st=ORANGE_ST, sw=2,
           dashed=True,
           text=("可解决：防幻觉免疫问答 · 可解释临床决策 · 健康/免疫报告解读 · 机制假设生成"),
           tsize=22, tcolor=ORANGE_ST)
    return c.dump()


# ============= 0.4 vs He-2026 同名 ICKG（共同基础 + 三栏对比）=============
def build_0_4():
    """对比本项目 ICKG 与同名的 He-2026 ICKG（npj Artif Intell 2026）。
    顶部横幅写『两者共同解决了什么』，下面三栏分别写：
    ①He-2026 解决了什么 ②He-2026 没解决/明确排除 ③本项目解决了什么。只写结论。"""
    c = Canvas()
    c.text("t", 100, 22, 1400, 48,
           "本项目 ICKG vs He-2026 同名 ICKG：解决了什么 / 没解决什么", size=32, color=C_TITLE)
    c.text("st", 80, 74, 1440, 28,
           "同源痛点、同种范式 → 但路线分叉：He-2026 止于『科研基因集注释』，本项目推进到『机制→临床全链路』",
           size=20, color=C_SUB)
    # 顶部横幅：两者共同解决了什么（蓝绿）
    c.rect("shared", 60, 110, 1460, 74, bg="#e6fcf5", st="#0ca678", sw=3,
           text=("两者共同解决的问题：把碎片化、不可计算的免疫学文献，用 LLM 自动抽取成\n"
                 "『实体-关系结构化、逐边可溯源 PMID、可检索可推理』的免疫细胞知识图谱（同名、同源痛点）"),
           tsize=19, tcolor="#0ca678")
    # 三列 x 起点（宽 460，列间距 40）。只写结论：解决了什么 / 没解决什么。
    cols = [
        ("a", 60, BLUE_BG, BLUE_ST, 2,
         "① He-2026 解决了什么",
         ("npj Artif Intell · 2026 · 同名 ICKG\n\n"
          "在共同基础上，聚焦解决\n"
          "『基因集注释』这一科研痛点：\n\n"
          "· 上下文特异、抗 LLM 幻觉\n"
          "· 细胞类型特异的机制解读\n"
          "· 服务单细胞 / 空间组学的\n"
          "  假设生成\n\n"
          "→ 定位：面向科研的\n"
          "　 基因集注释工具")),
        ("b", 560, RED_BG, RED_ST, 2,
         "② He-2026 没解决 / 明确排除",
         ("作者在 Discussion 自述的边界：\n\n"
          "· 关系仅 activation / inhibition\n"
          "  两类，缺定量与上下文语义\n"
          "· 仅大细胞类型，未到亚型 / 状态\n"
          "· 仅 4 个割裂子图，无统一全景\n"
          "· 语料仅限『癌症免疫治疗』\n"
          "· 无 drug / chemical /\n"
          "  intervention 等临床实体\n"
          "· 临床 / 转化应用\n"
          "  『超出本研究范围』")),
        ("c", 1060, GOLD_BG, GOLD_ST, 4,
         "③ 本项目 ICKG 解决了什么",
         ("在共同基础上，进一步推进到\n"
          "『机制→临床可执行』：\n\n"
          "· 一张免疫全景大图（非割裂子图）\n"
          "· 含 disease / intervention /\n"
          "  chemical 等临床可执行实体\n"
          "· 89 类有向 + 定量关系（非仅 2 类）\n"
          "· 语料覆盖免疫学全景（不止肿瘤）\n\n"
          "→ 机制→临床全闭环：检索 / 因果 /\n"
          "　 预测 / 报告解读 / ICI 响应")),
    ]
    for cid, x, bg, st, sw, head, body in cols:
        c.rect(cid + "h", x, 198, 460, 56, bg=bg, st=st, sw=sw,
               text=head, tsize=22, tcolor=st)
        c.rect(cid + "b", x, 262, 460, 348, bg=C_WHITE, st=st, sw=sw,
               text=body, tsize=18, tcolor=C_TEXT)
    # 主结论（绿）
    c.rect("concl", 60, 624, 1460, 80, bg=GREEN_BG, st=GREEN_ST, sw=3,
           dashed=True,
           text=("一句话：在『把免疫文献整合成可溯源知识图谱』这一共同成果之上，He-2026 止步于科研基因集注释（临床明确排除）；\n"
                 "本项目接续其自述局限，补上临床实体、89 类有向定量关系与机制→临床可执行能力。"),
           tsize=19, tcolor=GREEN_ST)
    # 共同开放挑战（橙，诚实标注）
    c.rect("share", 60, 716, 1460, 60, bg=ORANGE_BG, st=ORANGE_ST, sw=2,
           dashed=True,
           text=("两者共同的开放挑战：文献固有偏倚 · 摘要级抽取的覆盖上限 · 亚型/细胞状态粒度 · KGE/GNN 推理的充分验证 —— 本项目以此为后续迭代方向"),
           tsize=17, tcolor=ORANGE_ST)
    return c.dump()


# ===================== 顶层应用蓝图总览 =====================
def build_blueprint():
    c = Canvas()
    c.text("title", 100, 24, 1400, 50,
           "免疫细胞知识图谱（ICKG）应用蓝图", size=36, color=C_TITLE)
    c.text("subtitle", 80, 80, 1440, 32,
           "423,823 三元组 · 235,457 实体 · 19 实体类型 · 89 关系类型 · 12 应用场景 + 4 定位专题        ⭐ = 旗舰场景",
           size=20, color=C_SUB)
    # 定位横幅
    c.rect("posbar", 60, 122, 1480, 64, bg="#f8f0fc", st="#9c36b5", sw=2,
           text=("差异化定位（先回答“为什么是 ICKG”）：　0.1 vs 其他知识图谱　·　0.2 vs 大模型（会被淘汰吗）"
                 "　·　0.3 与最先进大模型如何结合　·　0.4 vs He-2026 同名 ICKG（深度对比）"),
           tsize=18, tcolor="#9c36b5")
    # 中心
    c.ellipse("ickg", 600, 212, 400, 76, bg="#74c0fc", st="#1971c2", sw=2,
              text="ICKG  免疫细胞知识图谱", tsize=24, tcolor="#0b3d6b",
              arrows=["a-know", "a-clin", "a-other"])
    # 三大分支
    c.rect("b-know", 60, 305, 420, 60, bg="#a5d8ff", st="#1971c2", sw=2,
           text="一、免疫知识智能服务", tsize=22, tcolor="#0b3d6b",
           arrows=["a-know"])
    c.rect("b-clin", 590, 305, 420, 60, bg="#b2f2bb", st="#2f9e44", sw=2,
           text="二、精准免疫医疗", tsize=22, tcolor="#13602a", arrows=["a-clin"])
    c.rect("b-other", 1120, 305, 420, 60, bg="#ffd6a5", st="#e8590c", sw=2,
           text="三、个人免疫健康管理", tsize=22, tcolor="#8a3a06",
           arrows=["a-other"])
    c.arrow("a-know", 790, 290, -480, 15, st=C_TEXT, sw=2,
            start_id="ickg", end_id="b-know")
    c.arrow("a-clin", 800, 290, 0, 15, st=C_TEXT, sw=2,
            start_id="ickg", end_id="b-clin")
    c.arrow("a-other", 810, 290, 520, 15, st=C_TEXT, sw=2,
            start_id="ickg", end_id="b-other")
    # 各分支 4 个场景
    scenes = {
        60: ("#e7f5ff", "#1971c2", "#0b3d6b", [
            "1.1  精准检索 & 即时问答",
            "1.2  防幻觉问答助手",
            "1.3  因果链解析 & 假说生成",
            "1.4  未知关联预测 & 选题"], None),
        590: ("#ebfbee", "#2f9e44", "#13602a", [
            "2.1  预防：免疫病风险预测",
            "2.2  诊断：辅助诊断与分型",
            "2.3  治疗：ICI 响应预测  ⭐",
            "2.4  预后：生存与进展评估"], 2),     # 第3行高亮
        1120: ("#fff4e6", "#e8590c", "#8a3a06", [
            "3.1  健康/免疫报告解读  ⭐",
            "3.2  免疫韧性画像 & 追踪",
            "3.3  个性化疫苗 & 免疫提升",
            "3.4  慢病/亚健康风险追踪"], 0),      # 第1行高亮
    }
    ys = [390, 475, 560, 645]
    for x, (bg, st, tc, labels, hl) in scenes.items():
        for i, (y, lab) in enumerate(zip(ys, labels)):
            if i == hl:
                bgc, stc, tcc, sw = GOLD_BG, GOLD_ST, "#8a3a06", 3
            else:
                bgc, stc, tcc, sw = bg, st, tc, 2
            c.rect(f"s-{x}-{i}", x, y, 420, 70, bg=bgc, st=stc, sw=sw,
                   text=lab, tsize=20, tcolor=tcc)
    # 技术栈
    c.rect("tech", 60, 748, 1480, 64, bg="#f1f3f5", st="#495057", sw=2,
           text=("技术栈：Neo4j (图数据库) · PyKEEN / RDF2Vec (KGE) · "
                 "PyTorch Geometric (GNN) · LangChain Graph-RAG · Baichuan-M2 (微调 LLM)"),
           tsize=20, tcolor="#495057")
    c.text("footer", 80, 828, 1440, 30,
           "Siyu Zhou  ·  2026-05-21  ·  数据源：PubMed 2016-2026  ·  方法学参考：Zhou-2026 LCKG  +  Gao-2025 MDKG",
           size=16, color=C_SUB)
    return c.dump()


BUILDERS = {
    "00_positioning/0.1_vs_other_kgs": build_0_1,
    "00_positioning/0.2_vs_llm": build_0_2,
    "00_positioning/0.3_kg_llm_synergy": build_0_3,
    "00_positioning/0.4_vs_he2026_ickg": build_0_4,
    "ICKG_application_blueprint": build_blueprint,
}


def main():
    p = argparse.ArgumentParser(description="批量生成 ICKG 差异化定位 Excalidraw 对比图")
    p.add_argument("--output-root", "-o", type=Path, required=True,
                   help="输出根目录（通常为 presentation/application）")
    p.add_argument("--scenarios", "-s", nargs="*", default=None,
                   help="只生成指定 path 的图；不指定则生成全部图")
    args = p.parse_args()

    targets = (list(BUILDERS) if not args.scenarios
               else [k for k in BUILDERS if k in args.scenarios])
    for key in targets:
        out = args.output_root / (key + ".excalidraw")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(BUILDERS[key](), ensure_ascii=False, indent=2),
                       encoding="utf-8")
        print(f"[OK] 生成 → {out}")
    print(f"\n共生成 {len(targets)} 个定位对比图")


if __name__ == "__main__":
    main()
