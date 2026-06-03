#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Run triple-extraction inference with the merged fine-tuned model on raw papers.
# 用合并后的微调模型对原始文章(Title+Abstract)做三元组抽取推理，供人工查看提取效果。
"""
读取文章 JSON（list，每篇含 Title/Abstract 等字段），按训练时一致的方式
（title.strip() + 空格 + abstract.strip()，连续空白压成单空格）拼成 user 文本，
配合精简版 system 提示词，调用 merged 模型生成三元组 JSON。

要点：
- system 提示词必须与训练一致（默认 prompts/Triple_prompt_v2_finetune.md）。
- 走 tokenizer 官方 chat template，add_generation_prompt=True，且【不传 thinking_mode】
  （训练分布里推理 prompt 末尾是 <|im_start|>assistant\n；传 thinking_mode 会注入 <think>，未训练）。
- 输出：结构化 JSON（原文 + 原始预测 + 解析后的三元组 + 合法性）与人类友好的 Markdown 表格，供人工核对。
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def merge_title_abstract(title: str, abstract: str) -> str:
    """与 04_build_sft_dataset.py 完全一致：title + 空格 + abstract，连续空白压成单空格。"""
    title_clean = (title or "").strip()
    abstract_clean = (abstract or "").strip()
    merged = f"{title_clean} {abstract_clean}".strip()
    return re.sub(r"\s+", " ", merged)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="用合并后的微调模型对文章做三元组抽取推理（供人工查看效果）")
    p.add_argument("--model-dir", "-m", default="models/Baichuan-M2-32B-QLoRA-v1/merged",
                   help="合并后的完整权重目录（默认：models/Baichuan-M2-32B-QLoRA-v1/merged）")
    p.add_argument("--input", "-i", required=True,
                   help="输入文章 JSON 路径（list，每篇含 Title/Abstract 字段）")
    p.add_argument("--prompt", "-p", default="prompts/Triple_prompt_v2_finetune.md",
                   help="system 提示词路径（须与训练一致，默认精简版 Triple_prompt_v2_finetune.md）")
    p.add_argument("--output", "-o", required=True,
                   help="输出 JSON 路径（会在同名 .md 另存人类友好版本）")
    p.add_argument("--title-field", default="Title", help="标题字段名（默认 Title）")
    p.add_argument("--abstract-field", default="Abstract", help="摘要字段名（默认 Abstract）")
    p.add_argument("--max-new-tokens", type=int, default=2560,
                   help="单篇最大生成 token 数（默认 2560，覆盖训练 assistant max≈2326）")
    p.add_argument("--temperature", type=float, default=0.1,
                   help="生成 temperature（默认 0.1，抽取任务要确定性）")
    p.add_argument("--device", default="auto", help="device_map（默认 auto）")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    in_path = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    md_path = out_path.with_suffix(".md")

    system_content = Path(args.prompt).read_text(encoding="utf-8").strip()
    papers = json.loads(in_path.read_text(encoding="utf-8"))
    if isinstance(papers, dict):
        papers = [papers]
    print(f"[加载] 文章 {len(papers)} 篇 | system 提示词 {len(system_content)} 字符 | 模型 {args.model_dir}")

    print("[加载] 模型与 tokenizer ...")
    tok = AutoTokenizer.from_pretrained(args.model_dir, trust_remote_code=True)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.model_dir, trust_remote_code=True, dtype=torch.bfloat16, device_map=args.device,
    )
    model.eval()

    results = []
    for idx, paper in enumerate(papers):
        title = str(paper.get(args.title_field, "") or "")
        abstract = str(paper.get(args.abstract_field, "") or "")
        user_content = merge_title_abstract(title, abstract)
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]
        # 不传 thinking_mode，保持与训练分布一致（末尾 <|im_start|>assistant\n）
        # return_dict=True：拿到含 input_ids/attention_mask 的 BatchEncoding，再 **inputs 传给 generate
        inputs = tok.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_tensors="pt", return_dict=True,
        ).to(model.device)
        prompt_len = inputs["input_ids"].shape[1]
        gen_kwargs = dict(max_new_tokens=args.max_new_tokens, do_sample=args.temperature > 0,
                          pad_token_id=tok.pad_token_id)
        if args.temperature > 0:
            gen_kwargs["temperature"] = args.temperature
        with torch.no_grad():
            out_ids = model.generate(**inputs, **gen_kwargs)
        gen_text = tok.decode(out_ids[0][prompt_len:], skip_special_tokens=True).strip()

        parsed = None
        n_tri = 0
        json_ok = False
        try:
            parsed = json.loads(gen_text)
            json_ok = isinstance(parsed, list)
            n_tri = len(parsed) if isinstance(parsed, list) else 0
        except Exception as e:
            parsed = {"_parse_error": str(e)}
        pmid = paper.get("PMID", "")
        print(f"  [{idx + 1}/{len(papers)}] PMID={pmid} | user {len(user_content)} chars "
              f"-> 生成 {len(gen_text)} chars | JSON合法={json_ok} | 三元组数={n_tri}")
        results.append({
            "index": idx,
            "PMID": pmid,
            "DOI": paper.get("DOI", ""),
            "Journal": paper.get("Journal", ""),
            "Title": title,
            "user_content": user_content,
            "json_valid": json_ok,
            "n_triples": n_tri,
            "triples": parsed if json_ok else None,
            "raw_prediction": gen_text,
        })

    payload = {
        "_meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model_dir": args.model_dir,
            "prompt_file": args.prompt,
            "input_file": str(in_path),
            "temperature": args.temperature,
            "max_new_tokens": args.max_new_tokens,
            "n_papers": len(papers),
        },
        "results": results,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[完成] 结构化结果 -> {out_path}")

    lines = [
        "# 三元组抽取结果（微调模型人工查看）\n",
        f"- 模型: `{args.model_dir}`",
        f"- 提示词: `{args.prompt}`（精简版）",
        f"- 生成时间: {payload['_meta']['generated_at']} | temperature={args.temperature}\n",
    ]
    for r in results:
        lines.append(f"\n---\n\n## [{r['index'] + 1}] PMID {r['PMID']} — {r['Journal']}")
        lines.append(f"**DOI**: {r['DOI']}\n")
        lines.append(f"**Title**: {r['Title']}\n")
        lines.append(f"**输入文本（user，{len(r['user_content'])} 字符）**:\n\n> {r['user_content']}\n")
        lines.append(f"**JSON 合法**: {r['json_valid']} | **三元组数**: {r['n_triples']}\n")
        if r["json_valid"] and r["triples"]:
            lines.append("| # | head [type] | relation | tail [type] | score | source_sentence |")
            lines.append("|---|---|---|---|---|---|")
            for i, t in enumerate(r["triples"]):
                if not isinstance(t, dict):
                    continue
                h = f"{t.get('head', '')} [{t.get('head_type', '')}]"
                rel = t.get("relation", "")
                ta = f"{t.get('tail', '')} [{t.get('tail_type', '')}]"
                sc = t.get("score", "")
                ss = str(t.get("source_sentence", "")).replace("|", "\|").replace("\n", " ")
                lines.append(f"| {i + 1} | {h} | {rel} | {ta} | {sc} | {ss} |")
        else:
            lines.append("```\n" + str(r["raw_prediction"])[:4000] + "\n```")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[完成] 人工查看版 -> {md_path}")


if __name__ == "__main__":
    main()
