#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Async client that streams inference-input shards to a vLLM OpenAI server, extracts
# triples, and writes them out incrementally with resume + throughput stats.
# 异步客户端：把推理输入分片高并发推送到 vLLM OpenAI 服务，抽取三元组，增量落盘，
# 支持断点续跑与端到端吞吐统计（带 --limit 即为「真实数据小样本 pilot」）。
"""
设计要点（务必理解）：
- 【对齐铁律】用本地 tokenizer 把 messages 渲染成 prompt 字符串后，走 /v1/completions 原样推理，
  绕开 vLLM chat 端点可能默认注入 thinking 的风险；渲染【不传 thinking_mode】，
  prompt 末尾必须是 `<|im_start|>assistant\\n`（启动时自检，不符合直接退出）。
- 为兼顾「精确」与「快」：先用 tokenizer 渲染一次带哨兵的模板，切出 PREFIX/SUFFIX，
  之后每条请求 prompt = PREFIX + user_content + SUFFIX（纯字符串拼接，与 tokenizer 逐字一致）。
- 输出对齐既有下游 schema：triples.jsonl 每行一条三元组
  {PMID, head, head_type, relation, tail, tail_type, source_sentence, score}。
- 断点续跑：done_pmids.txt 记录已成功 PMID，重启自动跳过；失败/截断分别记账。
- 架构：producer(渲染+去重) → input_queue → N 个 worker(纯 HTTP) → result_queue → 单 writer(落盘+统计)。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import aiohttp
from transformers import AutoTokenizer

EXPECTED_TAIL = "<|im_start|>assistant\n"
SENTINEL = "__USER_CONTENT__"


# ---------------- prompt 渲染（模板因式分解） ----------------
def build_prefix_suffix(tokenizer_dir: str, system_content: str):
    """渲染一次带哨兵的模板，切出 PREFIX/SUFFIX；同时做对齐自检。"""
    tok = AutoTokenizer.from_pretrained(tokenizer_dir, trust_remote_code=True)
    if not tok.chat_template:
        raise SystemExit("[错误] tokenizer.chat_template 为空，无法渲染")
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": SENTINEL},
    ]
    # 不传 thinking_mode：保持与训练分布一致（末尾 <|im_start|>assistant\n）
    full = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    if full.count(SENTINEL) != 1:
        raise SystemExit("[错误] 哨兵未在渲染结果中唯一出现，模板异常")
    prefix, suffix = full.split(SENTINEL)
    # 对齐铁律自检
    if not suffix.endswith(EXPECTED_TAIL):
        raise SystemExit(
            f"[失败] prompt 末尾不是 {EXPECTED_TAIL!r}，实际末尾：{suffix[-60:]!r}\n"
            f"        说明渲染路径被注入了 thinking 或模板被改坏，禁止上线。")
    if "<think>" in suffix:
        raise SystemExit("[失败] SUFFIX 含 <think>，与训练分布不符，禁止上线。")
    print(f"[OK] prompt 对齐自检通过：末尾 {EXPECTED_TAIL!r}，PREFIX {len(prefix)} 字符 / SUFFIX {len(suffix)} 字符")
    return prefix, suffix


# ---------------- 模型输出 → 三元组解析 ----------------
def strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def find_first_json_array(text: str):
    """从文本中截取第一个平衡的 JSON 数组块。"""
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


def parse_triples(model_text: str):
    """返回 (triples_list, ok)。容错：去 code fence、截首个 JSON 数组。"""
    cleaned = strip_code_fence(model_text)
    for candidate in (cleaned, find_first_json_array(cleaned)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return parsed, True
        except Exception:
            continue
    return [], False


def to_triple_rows(pmid: str, triples):
    """把一篇文章的三元组列表 explode 成对齐下游 schema 的单条记录。"""
    rows = []
    for t in triples:
        if not isinstance(t, dict):
            continue
        rows.append({
            "PMID": pmid,
            "head": t.get("head", ""),
            "head_type": t.get("head_type", ""),
            "relation": t.get("relation", ""),
            "tail": t.get("tail", ""),
            "tail_type": t.get("tail_type", ""),
            "source_sentence": t.get("source_sentence", ""),
            "score": t.get("score", ""),
        })
    return rows


# ---------------- 输入遍历 ----------------
def iter_input_files(input_path: str):
    p = Path(input_path)
    if p.is_dir():
        return sorted(p.glob("*.jsonl"))
    return [p]


def load_done_set(done_path: Path) -> set:
    done = set()
    if done_path.exists():
        with done_path.open("r", encoding="utf-8") as f:
            for line in f:
                pid = line.strip()
                if pid:
                    done.add(pid)
    return done


# ---------------- 主流程 ----------------
async def run(args):
    system_content = Path(args.prompt).read_text(encoding="utf-8").strip()
    prefix, suffix = build_prefix_suffix(args.tokenizer, system_content)

    out_dir = Path(args.output_dir)
    state_dir = out_dir / "_state"
    out_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    done_path = state_dir / "done_pmids.txt"
    done = load_done_set(done_path)
    print(f"[resume] 已完成 PMID = {len(done)}（将自动跳过）")

    # 输出句柄（行缓冲，增量落盘）
    f_tri = (out_dir / "triples.jsonl").open("a", encoding="utf-8", buffering=1)
    f_usage = (out_dir / "usage.jsonl").open("a", encoding="utf-8", buffering=1)
    f_fail = (out_dir / "failed.jsonl").open("a", encoding="utf-8", buffering=1)
    f_trunc = (out_dir / "truncated.jsonl").open("a", encoding="utf-8", buffering=1)
    f_done = done_path.open("a", encoding="utf-8", buffering=1)

    url = args.base_url.rstrip("/") + "/completions"
    headers = {"Authorization": f"Bearer {args.api_key}", "Content-Type": "application/json"}

    input_q: asyncio.Queue = asyncio.Queue(maxsize=args.concurrency * 4)
    result_q: asyncio.Queue = asyncio.Queue(maxsize=args.concurrency * 4)

    stats = {
        "submitted": 0, "ok": 0, "failed": 0, "truncated": 0, "empty_json": 0,
        "triples": 0, "prompt_tokens": 0, "completion_tokens": 0,
    }
    t0 = time.time()

    # ---- producer：读分片、跳过 done、渲染 prompt、入队 ----
    async def producer():
        n = 0
        for shard in iter_input_files(args.input):
            with shard.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    obj = json.loads(line)
                    pmid = str(obj["PMID"])
                    if pmid in done:
                        continue
                    prompt = prefix + obj["user_content"] + suffix
                    await input_q.put((pmid, prompt))
                    n += 1
                    if args.limit and n >= args.limit:
                        break
            if args.limit and n >= args.limit:
                break
        for _ in range(args.concurrency):
            await input_q.put(None)  # 毒丸，通知 worker 收工

    # ---- worker：纯 HTTP，请求 + 重试，结果入 result_q ----
    async def worker(session: aiohttp.ClientSession):
        while True:
            item = await input_q.get()
            if item is None:
                await result_q.put(("__worker_done__", None))
                return
            pmid, prompt = item
            payload = {
                "model": args.model,
                "prompt": prompt,
                "max_tokens": args.max_tokens,
                "temperature": args.temperature,
                "stream": False,
            }
            if args.stop:
                payload["stop"] = args.stop
            last_err = None
            for attempt in range(args.max_retries + 1):
                try:
                    async with session.post(url, json=payload, headers=headers,
                                            timeout=aiohttp.ClientTimeout(total=args.request_timeout)) as resp:
                        if resp.status != 200:
                            last_err = f"HTTP {resp.status}: {(await resp.text())[:200]}"
                            raise RuntimeError(last_err)
                        data = await resp.json()
                    await result_q.put(("ok", (pmid, data)))
                    break
                except Exception as e:  # 网络/超时/5xx → 退避重试
                    last_err = str(e)
                    if attempt < args.max_retries:
                        await asyncio.sleep(min(2 ** attempt, 10))
                    else:
                        await result_q.put(("err", (pmid, last_err)))

    # ---- writer：单协程落盘 + 统计 + 进度 ----
    async def writer():
        workers_left = args.concurrency
        last_print = time.time()
        while True:
            kind, body = await result_q.get()
            if kind == "__worker_done__":
                workers_left -= 1
                if workers_left == 0:
                    break
                continue
            if kind == "err":
                pmid, err = body
                f_fail.write(json.dumps({"PMID": pmid, "error": err}, ensure_ascii=False) + "\n")
                stats["failed"] += 1
            else:  # ok
                pmid, data = body
                choice = data["choices"][0]
                text = choice.get("text", "")
                finish = choice.get("finish_reason", "")
                usage = data.get("usage", {}) or {}
                stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
                stats["completion_tokens"] += usage.get("completion_tokens", 0)
                triples, ok = parse_triples(text)
                rows = to_triple_rows(pmid, triples)
                for r in rows:
                    f_tri.write(json.dumps(r, ensure_ascii=False) + "\n")
                stats["triples"] += len(rows)
                f_usage.write(json.dumps({
                    "PMID": pmid, "n_triples": len(rows), "json_valid": ok,
                    "finish_reason": finish,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                }, ensure_ascii=False) + "\n")
                if finish == "length":
                    f_trunc.write(json.dumps({"PMID": pmid, "completion_tokens":
                                              usage.get("completion_tokens", 0)}, ensure_ascii=False) + "\n")
                    stats["truncated"] += 1
                if not ok:
                    stats["empty_json"] += 1
                    f_fail.write(json.dumps({"PMID": pmid, "error": "json_parse_failed",
                                             "raw": text[:500]}, ensure_ascii=False) + "\n")
                f_done.write(pmid + "\n")
                stats["ok"] += 1

            # 周期性进度
            now = time.time()
            done_n = stats["ok"] + stats["failed"]
            if now - last_print >= args.print_every or done_n % 500 == 0:
                el = now - t0
                rps = done_n / el if el > 0 else 0
                otps = stats["completion_tokens"] / el if el > 0 else 0
                print(f"[{el:6.0f}s] 完成 {done_n}  成功 {stats['ok']}  失败 {stats['failed']}  "
                      f"截断 {stats['truncated']}  三元组 {stats['triples']}  | "
                      f"{rps:.2f} req/s  {otps:.0f} out-tok/s", flush=True)
                last_print = now

    async with aiohttp.ClientSession() as session:
        prod = asyncio.create_task(producer())
        workers = [asyncio.create_task(worker(session)) for _ in range(args.concurrency)]
        wr = asyncio.create_task(writer())
        await prod
        await asyncio.gather(*workers)
        await wr

    for h in (f_tri, f_usage, f_fail, f_trunc, f_done):
        h.close()

    # ---- 汇总 + 外推 ----
    el = time.time() - t0
    done_n = stats["ok"] + stats["failed"]
    rps = stats["ok"] / el if el > 0 else 0
    print("\n===== 汇总 =====")
    print(f"用时           : {el:.1f}s")
    print(f"成功/失败/截断 : {stats['ok']} / {stats['failed']} / {stats['truncated']}")
    print(f"JSON 解析失败  : {stats['empty_json']}")
    print(f"三元组总数     : {stats['triples']}  （平均 {stats['triples'] / max(1, stats['ok']):.1f} 条/篇）")
    print(f"prompt/comp tok: {stats['prompt_tokens']} / {stats['completion_tokens']}")
    print(f"吞吐           : {rps:.3f} 篇/s  ・ {stats['completion_tokens'] / el if el else 0:.0f} out-tok/s")
    if rps > 0 and args.extrapolate_total > 0:
        remain = args.extrapolate_total - len(done)
        hours = remain / rps / 3600
        print(f"\n[外推] 按当前 {rps:.3f} 篇/s，剩余 {remain} 篇 ≈ {hours:.1f} 小时 "
              f"（≈ {hours / 24:.1f} 天）")
        if args.gpu_hourly_cost > 0:
            print(f"[外推] 预计 GPU 费用 ≈ {hours * args.gpu_hourly_cost:.0f} 元"
                  f"（按 {args.gpu_hourly_cost} 元/小时）")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="把推理输入分片高并发推送到 vLLM 服务并抽取三元组（含断点续跑与吞吐外推）")
    p.add_argument("--input", "-i", default="data/vllm_inference/input_shards",
                   help="输入分片目录或单个 jsonl 文件（每行 {PMID,user_content}）")
    p.add_argument("--output-dir", "-o", default="data/vllm_inference/output",
                   help="输出目录（triples/usage/failed/truncated.jsonl 与 _state/done_pmids.txt）")
    p.add_argument("--base-url", default="http://127.0.0.1:8801/v1", help="vLLM OpenAI 服务基址（默认本机 8801）")
    p.add_argument("--api-key", default="EMPTY", help="vLLM 服务 API key（默认 EMPTY，vllm 默认不校验）")
    p.add_argument("--model", default="baichuan-m2-qlora", help="served-model-name（与 02_serve_vllm.sh 一致）")
    p.add_argument("--tokenizer", default="models/Baichuan-M2-32B-QLoRA-v1/merged",
                   help="渲染 prompt 用的 tokenizer 目录（含 chat_template，默认 merged）")
    p.add_argument("--prompt", "-p", default="prompts/Triple_prompt_v2_finetune.md",
                   help="system 提示词路径（须与训练一致，默认精简版）")
    p.add_argument("--concurrency", "-c", type=int, default=128, help="并发请求数（默认 128，压测后调）")
    p.add_argument("--max-tokens", type=int, default=2560, help="单篇最大生成 token（默认 2560，覆盖训练 max≈2326）")
    p.add_argument("--temperature", type=float, default=0.1, help="生成 temperature（默认 0.1，抽取要确定性）")
    p.add_argument("--stop", nargs="*", default=None, help="可选停止符（如 <|im_end|>），默认靠模型 eos 停止")
    p.add_argument("--max-retries", type=int, default=3, help="单请求失败最大重试次数（默认 3，指数退避）")
    p.add_argument("--request-timeout", type=float, default=600.0, help="单请求超时秒数（默认 600）")
    p.add_argument("--limit", type=int, default=0, help="只处理前 N 篇（>0 即为真实数据小样本 pilot；默认 0=全量）")
    p.add_argument("--print-every", type=float, default=15.0, help="进度打印最小间隔秒（默认 15）")
    p.add_argument("--extrapolate-total", type=int, default=684153,
                   help="外推用的待抽取总数（默认 684153，剩余全量）")
    p.add_argument("--gpu-hourly-cost", type=float, default=0.0, help="GPU 单价(元/小时)，>0 则外推费用")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(run(parse_args()))
