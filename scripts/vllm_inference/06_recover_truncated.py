#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Recovery pass for truncated articles: re-extract with a larger token budget and an
# anti-repetition temperature, then union-merge with the original triples (only adds, never drops).
# 补尾重跑：对主全量被截断(finish_reason=length)的文章，用更大 max_tokens + 抗复读温度重抽，
# 与原三元组取并集去重，补回原上限丢掉的尾部三元组。只增不减；支持断点续跑。
"""
两步用法：
  1) 补尾重抽(默认)：对 output-dir/truncated.jsonl 里的 PMID 逐篇重抽，与原结果并集去重，
     写到 output-dir/recover/recovered.jsonl(每行一条三元组) + _state/recovered_pmids.txt(续跑)。
  2) 合并(加 --apply 或 --merge-only)：生成最终 triples_merged.jsonl
     = 非截断 PMID 原三元组 + 已补尾截断 PMID 的并集(未补尾的截断 PMID 保留原三元组)。流式、写新文件、不覆盖原文件。
对齐铁律同 03：走 /v1/completions 自渲染、不传 thinking_mode、prompt 末尾须 <|im_start|>assistant。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

import aiohttp
from transformers import AutoTokenizer

NL = chr(10)
BSL = chr(92)
EXPECTED_TAIL = "<|im_start|>assistant" + NL
SENTINEL = "__USER_CONTENT__"
TRIPLE_KEYS = ("head", "head_type", "relation", "tail", "tail_type")


def build_prefix_suffix(tokenizer_dir, system_content):
    tok = AutoTokenizer.from_pretrained(tokenizer_dir, trust_remote_code=True)
    if not tok.chat_template:
        raise SystemExit("[错误] tokenizer.chat_template 为空")
    messages = [{"role": "system", "content": system_content},
                {"role": "user", "content": SENTINEL}]
    full = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    if full.count(SENTINEL) != 1:
        raise SystemExit("[错误] 哨兵未在渲染结果中唯一出现")
    prefix, suffix = full.split(SENTINEL)
    if not suffix.endswith(EXPECTED_TAIL):
        raise SystemExit("[失败] prompt 末尾不是 <|im_start|>assistant，禁止上线")
    if "<think>" in suffix:
        raise SystemExit("[失败] SUFFIX 含 <think>，与训练分布不符")
    print("[OK] prompt 对齐自检通过(末尾 <|im_start|>assistant)")
    return prefix, suffix


def strip_code_fence(text):
    t = text.strip()
    if t.startswith("```"):
        nl = t.find(NL)
        if nl != -1:
            t = t[nl + 1:]
        t = t.rstrip()
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def salvage_objects(text):
    objs = []
    depth = 0
    start = None
    in_str = False
    esc = False
    for i, c in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif c == BSL:
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0 and start is not None:
                    try:
                        objs.append(json.loads(text[start:i + 1]))
                    except Exception:
                        pass
                    start = None
    return objs


def parse_triples(text):
    cleaned = strip_code_fence(text)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list) and parsed:
            return parsed
    except Exception:
        pass
    return salvage_objects(cleaned)


def triple_key(t):
    return tuple(str(t.get(k, "")) for k in TRIPLE_KEYS)


def dedup_union(*triple_lists):
    """按 5 元组键去重的并集，先出现者优先(原结果在前→稳定、只增不减)。"""
    rows = []
    seen = set()
    for lst in triple_lists:
        for t in lst:
            if not isinstance(t, dict):
                continue
            k = triple_key(t)
            if k in seen:
                continue
            seen.add(k)
            rows.append(t)
    return rows


def normalize_row(pmid, t):
    return {
        "PMID": pmid,
        "head": t.get("head", ""), "head_type": t.get("head_type", ""),
        "relation": t.get("relation", ""),
        "tail": t.get("tail", ""), "tail_type": t.get("tail_type", ""),
        "source_sentence": t.get("source_sentence", ""), "score": t.get("score", ""),
    }


def load_truncated_pmids(output_dir):
    res, seen = [], set()
    p = output_dir / "truncated.jsonl"
    if not p.exists():
        return res
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            pid = str(json.loads(line)["PMID"])
            if pid not in seen:
                seen.add(pid)
                res.append(pid)
    return res


def load_existing_triples(output_dir, pmid_set):
    d = {}
    with (output_dir / "triples.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            pid = str(o["PMID"])
            if pid in pmid_set:
                d.setdefault(pid, []).append(o)
    return d


def load_user_contents(shards_dir, pmid_set):
    d = {}
    for sh in sorted(Path(shards_dir).glob("*.jsonl")):
        with sh.open(encoding="utf-8") as f:
            for line in f:
                o = json.loads(line)
                pid = str(o["PMID"])
                if pid in pmid_set:
                    d[pid] = o["user_content"]
        if len(d) == len(pmid_set):
            break
    return d


def load_done(done_path):
    if not done_path.exists():
        return set()
    return set(x.strip() for x in done_path.open(encoding="utf-8") if x.strip())


async def recover(args):
    system_content = Path(args.prompt).read_text(encoding="utf-8").strip()
    prefix, suffix = build_prefix_suffix(args.tokenizer, system_content)
    output_dir = Path(args.output_dir)
    recover_dir = output_dir / args.recover_subdir
    state_dir = recover_dir / "_state"
    recover_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    done_path = state_dir / "recovered_pmids.txt"

    trunc_list = load_truncated_pmids(output_dir)
    trunc_set = set(trunc_list)
    done = load_done(done_path)
    existing = load_existing_triples(output_dir, trunc_set)
    ucs = load_user_contents(args.shards, trunc_set)
    todo = [p for p in trunc_list if p not in done and p in ucs]
    print(f"[load] 截断 {len(trunc_set)} | 已补尾 {len(done)} | 本次待处理 {len(todo)}")
    if not todo:
        print("[done] 没有待补尾的 PMID")
        return

    f_rec = (recover_dir / "recovered.jsonl").open("a", encoding="utf-8", buffering=1)
    f_done = done_path.open("a", encoding="utf-8", buffering=1)
    url = args.base_url.rstrip("/") + "/completions"
    headers = {"Authorization": "Bearer " + args.api_key, "Content-Type": "application/json"}
    input_q = asyncio.Queue(maxsize=args.concurrency * 4)
    result_q = asyncio.Queue(maxsize=args.concurrency * 4)
    stats = {"ok": 0, "err": 0, "added": 0, "kept": 0}
    t0 = time.time()

    async def producer():
        for pid in todo:
            await input_q.put((pid, prefix + ucs[pid] + suffix))
        for _ in range(args.concurrency):
            await input_q.put(None)

    async def worker(session):
        while True:
            item = await input_q.get()
            if item is None:
                await result_q.put(("__done__", None))
                return
            pid, prompt = item
            payload = {"model": args.model, "prompt": prompt, "max_tokens": args.max_tokens,
                       "temperature": args.temperature, "stream": False}
            last = None
            for attempt in range(args.max_retries + 1):
                try:
                    async with session.post(url, json=payload, headers=headers,
                                            timeout=aiohttp.ClientTimeout(total=args.request_timeout)) as resp:
                        if resp.status != 200:
                            last = "HTTP " + str(resp.status)
                            raise RuntimeError(last)
                        data = await resp.json()
                    await result_q.put(("ok", (pid, data)))
                    break
                except Exception as e:
                    last = str(e)
                    if attempt < args.max_retries:
                        await asyncio.sleep(min(2 ** attempt, 10))
                    else:
                        await result_q.put(("err", (pid, last)))

    async def writer():
        left = args.concurrency
        last_print = time.time()
        while True:
            kind, body = await result_q.get()
            if kind == "__done__":
                left -= 1
                if left == 0:
                    break
                continue
            pid = body[0]
            old = existing.get(pid, [])
            if kind == "err":
                union = dedup_union(old)
                stats["err"] += 1
            else:
                recovered = parse_triples(body[1]["choices"][0].get("text", ""))
                union = dedup_union(old, recovered)
                stats["ok"] += 1
                stats["kept"] += len(old)
                stats["added"] += max(0, len(union) - len(old))
            for t in union:
                f_rec.write(json.dumps(normalize_row(pid, t), ensure_ascii=False) + NL)
            f_done.write(pid + NL)
            now = time.time()
            if now - last_print >= args.print_every:
                el = now - t0
                total = stats["ok"] + stats["err"]
                print(f"[{el:6.0f}s] 补尾 {total}/{len(todo)}  净增三元组 {stats['added']}  "
                      f"失败 {stats['err']}  {total / el if el else 0:.2f} 篇/s", flush=True)
                last_print = now

    async with aiohttp.ClientSession() as session:
        prod = asyncio.create_task(producer())
        workers = [asyncio.create_task(worker(session)) for _ in range(args.concurrency)]
        wr = asyncio.create_task(writer())
        await prod
        await asyncio.gather(*workers)
        await wr
    for h in (f_rec, f_done):
        h.close()
    print(f"[完成] 补尾成功 {stats['ok']} / 失败 {stats['err']}；净增三元组 {stats['added']}(原保留 {stats['kept']})")
    if args.apply:
        do_merge(args)


def do_merge(args):
    output_dir = Path(args.output_dir)
    recover_dir = output_dir / args.recover_subdir
    recovered_path = recover_dir / "recovered.jsonl"
    if not recovered_path.exists():
        raise SystemExit("[错误] 缺少 recovered.jsonl，请先运行补尾重抽")
    recovered_pmids = load_done(recover_dir / "_state" / "recovered_pmids.txt")
    trunc_all = set(load_truncated_pmids(output_dir))
    not_recovered = trunc_all - recovered_pmids
    if not_recovered:
        print(f"[merge][提醒] {len(not_recovered)} 个截断 PMID 尚未补尾，将保留其原三元组")
    merged = Path(args.merged_out)
    out = merged.open("w", encoding="utf-8")
    n_keep = 0
    with (output_dir / "triples.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            pid = str(json.loads(line)["PMID"])
            if pid in recovered_pmids:
                continue
            out.write(line + NL)
            n_keep += 1
    n_rec = 0
    with recovered_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.write(line + NL)
                n_rec += 1
    out.close()
    print(f"[merge] 非截断+未补尾保留 {n_keep} 条 + 已补尾并集 {n_rec} 条 -> {merged}")


def parse_args():
    p = argparse.ArgumentParser(description="对主全量被截断的文章补尾重抽并与原结果并集去重(只增不减，支持续跑)")
    p.add_argument("--output-dir", "-o", default="data/vllm_inference/output",
                   help="主全量输出目录(含 triples.jsonl 与 truncated.jsonl)")
    p.add_argument("--shards", default="data/vllm_inference/input_shards", help="推理输入分片目录(取 user_content)")
    p.add_argument("--recover-subdir", default="recover", help="补尾结果子目录(默认 output-dir/recover)")
    p.add_argument("--base-url", default="http://127.0.0.1:8801/v1", help="vLLM 服务基址")
    p.add_argument("--model", default="baichuan-m2-qlora", help="served-model-name")
    p.add_argument("--tokenizer", default="models/Baichuan-M2-32B-QLoRA-v1/merged", help="渲染 prompt 的 tokenizer 目录")
    p.add_argument("--prompt", "-p", default="prompts/Triple_prompt_v2_finetune.md", help="system 提示词路径")
    p.add_argument("--api-key", default="EMPTY", help="vLLM API key(默认 EMPTY)")
    p.add_argument("--concurrency", "-c", type=int, default=16, help="并发数(补尾上限更大、单请求更重，默认 16)")
    p.add_argument("--max-tokens", type=int, default=6144, help="补尾最大生成 token(默认 6144，给超长文章足够空间)")
    p.add_argument("--temperature", type=float, default=0.5, help="补尾温度(默认 0.5，抗复读、逃离 temp0 循环)")
    p.add_argument("--max-retries", type=int, default=3, help="单请求最大重试次数(默认 3)")
    p.add_argument("--request-timeout", type=float, default=900.0, help="单请求超时秒数(默认 900)")
    p.add_argument("--print-every", type=float, default=15.0, help="进度打印最小间隔秒(默认 15)")
    p.add_argument("--apply", action="store_true", help="补尾全部完成后自动生成最终合并文件")
    p.add_argument("--merge-only", action="store_true", help="只做合并、不重抽(用已存在的 recovered.jsonl)")
    p.add_argument("--merged-out", default="data/vllm_inference/output/triples_merged.jsonl", help="最终合并输出路径")
    return p.parse_args()


def main():
    args = parse_args()
    if args.merge_only:
        do_merge(args)
        return
    asyncio.run(recover(args))


if __name__ == "__main__":
    main()
