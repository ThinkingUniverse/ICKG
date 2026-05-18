#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Merge LoRA adapter back into the base model, save standalone bf16 checkpoint, and optionally run a few inference samples.
# 把训练好的 LoRA 适配器合并回基础模型，保存为可独立加载的 bfloat16 完整权重；可选在 test.jsonl 上跑少量样本验证。
"""
注意：4bit 量化下不能直接 merge_and_unload，需要先以 bfloat16 全精度重新加载基础模型，
然后挂上 LoRA 适配器并合并，最后保存。该过程显存占用较高（32B × 2 bytes ≈ 64GB），A100 80GB 推荐 device=auto 走 GPU。

启动示例：
    conda activate ickg
    # 仅合并保存：
    python src/Fine_tuning/training/merge_lora.py \
        --config src/Fine_tuning/configs/train_config.yaml \
        --device auto

    # 合并后在 test.jsonl 前 5 条样本上跑推理对比：
    python src/Fine_tuning/training/merge_lora.py \
        --config src/Fine_tuning/configs/train_config.yaml \
        --device auto \
        --test-after-merge 5
"""

from __future__ import annotations

# ============================================================
# 与 train_qlora.py 一致：先从 yaml env 段写 os.environ，
# 再 import HF 库，这样 HF_ENDPOINT / HF_HOME 生效。
# ============================================================
import os
import sys
from pathlib import Path

import yaml


def _bootstrap_env_from_config() -> None:
    cfg_path = None
    for flag in ("--config", "-c"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                cfg_path = sys.argv[i + 1]
                break
    if not cfg_path or not Path(cfg_path).exists():
        return
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            env_block = (yaml.safe_load(f).get("env") or {})
    except Exception:
        return
    for k, v in env_block.items():
        if v is None:
            continue
        os.environ.setdefault(k, str(v))


_bootstrap_env_from_config()

import argparse
import json

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把 LoRA 适配器合并到基础模型并另存完整权重，可选跑几条样本推理")
    parser.add_argument(
        "--config", "-c", required=True,
        help="训练配置 yaml 路径（与 train_qlora.py 共用）",
    )
    parser.add_argument(
        "--adapter-dir", default=None,
        help="LoRA 适配器目录，留空取 yaml 的 adapter_dir",
    )
    parser.add_argument(
        "--output-dir", "-o", default=None,
        help="合并后权重输出目录，留空取 yaml 的 merged_dir",
    )
    parser.add_argument(
        "--base-model", default=None,
        help="基础模型 HF 名或本地路径，留空取 yaml 的 model.name_or_path",
    )
    parser.add_argument(
        "--device", choices=["auto", "cpu", "cuda"], default="auto",
        help="加载基础模型使用的设备（默认 auto；显存不足时强制 cpu）",
    )
    parser.add_argument(
        "--torch-dtype", choices=["bfloat16", "float16"], default="bfloat16",
        help="合并时使用的精度（默认 bfloat16）",
    )
    parser.add_argument(
        "--test-after-merge", type=int, default=0, metavar="N",
        help="合并后在 test.jsonl 前 N 条样本上跑推理并打印对比（默认 0 = 跳过）",
    )
    parser.add_argument(
        "--test-max-new-tokens", type=int, default=2048,
        help="推理时单条最大生成 token 数（默认 2048，覆盖训练集 assistant max=2326 的绝大多数）",
    )
    parser.add_argument(
        "--test-temperature", type=float, default=0.1,
        help="推理 temperature（默认 0.1，抽取任务要确定性）",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_inference_test(
    model,
    tokenizer,
    test_jsonl_path: Path,
    n_samples: int,
    max_new_tokens: int,
    temperature: float,
) -> None:
    """合并后在 test.jsonl 前 N 条上跑生成，打印 user / ground-truth / prediction 对比，
    并对 prediction 做 JSON 合法性速查。仅用于人工 sanity check，不是正式评估。"""
    if n_samples <= 0:
        return
    if not test_jsonl_path.exists():
        print(f"[警告] test 文件不存在，跳过推理测试：{test_jsonl_path}")
        return

    # 读取前 N 条样本
    samples: list[dict] = []
    with open(test_jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if len(samples) >= n_samples:
                break
            line = line.strip()
            if line:
                samples.append(json.loads(line))

    print(f"\n{'=' * 80}\n[推理测试] 在 test.jsonl 前 {len(samples)} 条样本上跑生成\n{'=' * 80}")

    model.eval()
    device = next(model.parameters()).device                 # device_map='auto' 时取输入层所在 device

    for i, sample in enumerate(samples, 1):
        msgs = sample["messages"]
        # 把 system + user 作为输入（丢掉 ground-truth assistant）
        prompt_msgs = [m for m in msgs if m["role"] in ("system", "user")]
        ground_truth = next((m["content"] for m in msgs if m["role"] == "assistant"), "")

        # 应用 chat template，添加 generation prompt
        try:
            text = tokenizer.apply_chat_template(
                prompt_msgs,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,                       # Qwen3-style 模板支持；关闭 thinking
            )
        except TypeError:
            # 老模板不支持 enable_thinking 参数
            text = tokenizer.apply_chat_template(
                prompt_msgs, tokenize=False, add_generation_prompt=True,
            )

        inputs = tokenizer([text], return_tensors="pt").to(device)

        with torch.no_grad():
            gen_ids = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=(temperature > 0),
                temperature=temperature if temperature > 0 else 1.0,
                top_p=0.95,
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            )

        output_ids = gen_ids[0][inputs.input_ids.shape[1]:].tolist()
        pred = tokenizer.decode(output_ids, skip_special_tokens=True).strip()

        # 抽 user 内容前 200 字便于打印
        user_content = next((m["content"] for m in prompt_msgs if m["role"] == "user"), "")
        user_preview = user_content[:200] + ("..." if len(user_content) > 200 else "")
        gt_preview = ground_truth[:500] + ("..." if len(ground_truth) > 500 else "")
        pred_preview = pred[:500] + ("..." if len(pred) > 500 else "")

        print(f"\n--- Sample {i}/{len(samples)} | PMID: {sample.get('PMID', 'N/A')} ---")
        print(f"[USER (前 200 字)]\n  {user_preview}")
        print(f"\n[GROUND-TRUTH (前 500 字)]\n  {gt_preview}")
        print(f"\n[MODEL 输出 (前 500 字)]\n  {pred_preview}")

        # JSON 合法性速查
        try:
            parsed = json.loads(pred)
            if isinstance(parsed, list):
                print(f"\n[质量速查] JSON 合法 ✅  抽出 {len(parsed)} 条三元组")
            else:
                print(f"\n[质量速查] JSON 合法但顶层不是数组 ⚠️ (type={type(parsed).__name__})")
        except json.JSONDecodeError as e:
            print(f"\n[质量速查] JSON 解析失败 ❌  {e.msg[:100]}")

    print(f"\n{'=' * 80}\n[推理测试] 完成 {len(samples)} 条样本\n{'=' * 80}\n")


def main() -> None:
    args = parse_args()
    cfg = load_config(Path(args.config))
    repo_root = Path(__file__).resolve().parents[3]

    base_model = args.base_model or cfg["model"]["name_or_path"]
    adapter_dir = Path(args.adapter_dir) if args.adapter_dir else repo_root / cfg["adapter_dir"]
    output_dir = Path(args.output_dir) if args.output_dir else repo_root / cfg["merged_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)

    if not adapter_dir.exists():
        sys.exit(f"[错误] LoRA 适配器目录不存在：{adapter_dir}")

    dtype = torch.bfloat16 if args.torch_dtype == "bfloat16" else torch.float16
    device_map = args.device if args.device != "auto" else "auto"

    print(f"[加载] 基础模型：{base_model}  dtype={args.torch_dtype}  device_map={device_map}")
    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        dtype=dtype,                                # transformers 4.45+ 使用 dtype 替代 torch_dtype
        device_map=device_map,
        trust_remote_code=cfg["model"].get("trust_remote_code", True),
    )

    print(f"[加载] LoRA 适配器：{adapter_dir}")
    model = PeftModel.from_pretrained(base, str(adapter_dir))

    print("[合并] merge_and_unload ...")
    model = model.merge_and_unload()

    print(f"[保存] → {output_dir}")
    model.save_pretrained(str(output_dir), safe_serialization=True)

    tokenizer = AutoTokenizer.from_pretrained(
        str(adapter_dir), trust_remote_code=cfg["model"].get("trust_remote_code", True),
    )
    tokenizer.save_pretrained(str(output_dir))

    print(f"[完成] 完整权重已保存：{output_dir}")
    print("       可直接用 AutoModelForCausalLM.from_pretrained(<dir>, trust_remote_code=True) 加载推理。")

    # ------------------------------------------------------------------ #
    # 可选：在 test.jsonl 前 N 条样本上跑推理对比                              #
    # ------------------------------------------------------------------ #
    if args.test_after_merge > 0:
        # 推理时显式开启 KV cache，否则 generate 会逐 token 重算 attention，速度慢 5-10x
        model.config.use_cache = True
        if hasattr(model, "generation_config") and model.generation_config is not None:
            model.generation_config.use_cache = True

        sft_block = cfg.get("sft", {})
        test_path = repo_root / sft_block["data_path"] / sft_block.get("test_file", "test.jsonl")
        run_inference_test(
            model=model,                                # 已合并好、还在显存里的模型
            tokenizer=tokenizer,
            test_jsonl_path=test_path,
            n_samples=args.test_after_merge,
            max_new_tokens=args.test_max_new_tokens,
            temperature=args.test_temperature,
        )


if __name__ == "__main__":
    main()
