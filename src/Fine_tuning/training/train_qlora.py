#!/usr/bin/env python
# -*- coding: utf-8 -*-
# QLoRA fine-tuning of Baichuan-M2-32B via PEFT + BitsAndBytes + TRL SFTTrainer.
# 通过 PEFT + BitsAndBytes 4bit + TRL SFTTrainer 对 Baichuan-M2-32B 做 QLoRA 微调。
"""
所有超参从 --config 指向的 yaml 读取，脚本本身不写死任何模型/训练参数。

启动示例：
    conda activate lckg
    python src/Fine_tuning/training/train_qlora.py \
        --config src/Fine_tuning/configs/train_config.yaml

可选：
    --resume-from-checkpoint <ckpt_path>   从指定 checkpoint 继续训练
    --max-train-samples N                  小规模验证（仅取前 N 条训练样本）
"""

from __future__ import annotations

# ============================================================
# 关键：在导入任何 HF 库之前，先从 --config / -c 指向的 yaml 读取 env 段
# 并写到 os.environ。这样 HF_ENDPOINT（镜像）/ HF_HOME（缓存路径）生效。
# ============================================================
import os
import sys
from pathlib import Path

import yaml


def _bootstrap_env_from_config() -> None:
    """命令行扫描 --config/-c 路径，读取 yaml 的 env 段写入 os.environ"""
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
        os.environ.setdefault(k, str(v))   # 已有同名环境变量优先


_bootstrap_env_from_config()

# ============================================================
# 现在可以安全导入 HF / Torch 相关库
# ============================================================
import argparse
from typing import Any

import torch
from datasets import load_dataset
from peft import LoraConfig, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    set_seed,
)
from trl import SFTConfig, SFTTrainer


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baichuan-M2-32B QLoRA 微调主脚本（所有超参从 yaml 读取）"
    )
    parser.add_argument(
        "--config", "-c", required=True,
        help="训练配置 yaml 路径，例如 src/Fine_tuning/configs/train_config.yaml",
    )
    parser.add_argument(
        "--resume-from-checkpoint", default=None,
        help="从指定 checkpoint 路径继续训练（可选）",
    )
    parser.add_argument(
        "--max-train-samples", type=int, default=None,
        help="只取前 N 条训练样本，用于快速烟测（可选）",
    )
    parser.add_argument(
        "--max-eval-samples", type=int, default=None,
        help="只取前 N 条验证样本，用于快速烟测（可选）",
    )
    parser.add_argument(
        "--max-steps", type=int, default=None,
        help="覆盖 num_train_epochs，强制最多训练 N 步，用于烟测（可选）",
    )
    return parser.parse_args()


# --------------------------------------------------------------------------- #
# 配置加载与工具                                                                #
# --------------------------------------------------------------------------- #

def load_config(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def dtype_from_str(name: str) -> torch.dtype:
    """字符串 dtype 转 torch.dtype"""
    return {
        "bfloat16": torch.bfloat16,
        "float16":  torch.float16,
        "float32":  torch.float32,
    }[name]


def resolve_dataset_paths(cfg: dict, repo_root: Path) -> tuple[Path, Path]:
    """解析训练/验证数据路径（在仓库根下）"""
    sft = cfg["sft"]
    base = repo_root / sft["data_path"]
    train_path = base / sft["train_file"]
    val_path   = base / sft["val_file"]
    if not train_path.exists():
        sys.exit(f"[错误] 训练集不存在：{train_path}")
    if not val_path.exists():
        sys.exit(f"[错误] 验证集不存在：{val_path}")
    return train_path, val_path


def maybe_init_swanlab(cfg: dict) -> None:
    """如果 report_to 含 swanlab 则按 yaml 配置初始化一个 swanlab run；
    HF Trainer 会自动检测活动 run 并写入指标。API key 不在代码里，
    依赖服务器上预先执行过 `swanlab login`。"""
    report_to = cfg["training"].get("report_to", [])
    sw_cfg = cfg.get("swanlab") or {}
    if "swanlab" not in report_to or not sw_cfg.get("enabled", False):
        return
    try:
        import swanlab
    except ImportError:
        print("[警告] report_to 含 swanlab 但未安装 swanlab；请 `pip install swanlab`，本次跳过。", file=sys.stderr)
        return
    # trl 0.16+ 用 max_length（取代旧 max_seq_length），这里同样做兼容回退
    sft_block = cfg.get("sft", {})
    max_length_value = sft_block.get("max_length") or sft_block.get("max_seq_length")

    swanlab.init(
        project=sw_cfg.get("project", "ICKG"),
        workspace=sw_cfg.get("workspace"),
        experiment_name=sw_cfg.get("experiment_name"),
        description=sw_cfg.get("description"),
        mode=sw_cfg.get("mode", "cloud"),
        config={                                  # 把关键超参写进 swanlab 便于多 run 对比
            "model": cfg["model"]["name_or_path"],
            "max_length": max_length_value,
            "lora_r": cfg["lora"]["r"],
            "lora_alpha": cfg["lora"]["lora_alpha"],
            "learning_rate": cfg["training"]["learning_rate"],
            "num_train_epochs": cfg["training"]["num_train_epochs"],
            "effective_batch_size":
                cfg["training"]["per_device_train_batch_size"]
                * cfg["training"]["gradient_accumulation_steps"],
            "load_in_4bit": cfg["quantization"]["load_in_4bit"],
            "bnb_4bit_quant_type": cfg["quantization"]["bnb_4bit_quant_type"],
            "optim": cfg["training"]["optim"],
            "seed": cfg.get("seed", 42),
        },
    )
    print(f"[SwanLab] 已初始化 workspace={sw_cfg.get('workspace')} "
          f"project={sw_cfg.get('project')} "
          f"experiment={sw_cfg.get('experiment_name')} mode={sw_cfg.get('mode')}")


# --------------------------------------------------------------------------- #
# 主流程                                                                       #
# --------------------------------------------------------------------------- #

def main() -> None:
    args = parse_args()
    cfg = load_config(Path(args.config))

    # 随机种子
    seed = cfg.get("seed", 42)
    set_seed(seed)

    repo_root = Path(__file__).resolve().parents[3]
    train_path, val_path = resolve_dataset_paths(cfg, repo_root)

    # ------------------------------------------------------------------ #
    # 1. 4-bit 量化配置                                                    #
    # ------------------------------------------------------------------ #
    qcfg = cfg["quantization"]
    bnb_cfg = BitsAndBytesConfig(
        load_in_4bit=qcfg["load_in_4bit"],
        bnb_4bit_quant_type=qcfg["bnb_4bit_quant_type"],
        bnb_4bit_use_double_quant=qcfg["bnb_4bit_use_double_quant"],
        bnb_4bit_compute_dtype=dtype_from_str(qcfg["bnb_4bit_compute_dtype"]),
    )
    print(f"[量化] {qcfg}")

    # ------------------------------------------------------------------ #
    # 2. 加载 tokenizer 与 4bit 模型                                       #
    # ------------------------------------------------------------------ #
    mcfg = cfg["model"]
    print(f"[模型] 加载 {mcfg['name_or_path']} ...")

    tokenizer = AutoTokenizer.from_pretrained(
        mcfg["name_or_path"],
        trust_remote_code=mcfg.get("trust_remote_code", True),
        use_fast=True,
    )
    if tokenizer.pad_token is None:
        # Baichuan 等模型可能没有 pad_token，使用 eos_token 兜底
        tokenizer.pad_token = tokenizer.eos_token

    # trl 0.16+ 在 assistant_only_loss=True 时同时要求两件事：
    #   (a) chat_template 里含字面 "{% generation %}" 标记；
    #   (b) prefix-preservation —— 即 apply_chat_template(msgs[:k]) 必须是 apply_chat_template(msgs[:k+1]) 的前缀。
    # Baichuan-M2-32B 自带模板两条都不满足，且不在 trl 的自动 patch 白名单内。
    # 解决方案：训练期间用同目录下的简化版模板（去掉 tools/think 反向扫描，对每条 assistant 一视同仁），
    # 保存 adapter 前再把官方模板写回，确保 adapter/ 目录里的 tokenizer 与 base 模型字节一致。
    original_chat_template: str | None = None
    if cfg.get("sft", {}).get("assistant_only_loss"):
        tpl_path = Path(__file__).resolve().parent / "baichuan_m2_training_template.jinja"
        if tpl_path.exists():
            original_chat_template = tokenizer.chat_template
            tokenizer.chat_template = tpl_path.read_text(encoding="utf-8")
            print(f"[ChatTemplate] 训练期间已切换到简化模板：{tpl_path.name}（保存前会还原为官方模板）")
        else:
            sys.exit(
                f"[错误] assistant_only_loss=True 但未找到训练用 chat_template：{tpl_path}\n"
                f"        请确认 baichuan_m2_training_template.jinja 与本脚本同目录。"
            )

    model_kwargs: dict[str, Any] = {}
    attn_impl = mcfg.get("attn_implementation")
    if attn_impl:
        model_kwargs["attn_implementation"] = attn_impl                # e.g. "flash_attention_2"

    # transformers 4.45+ 用 `dtype`（替代旧 `torch_dtype`）；同时给出兼容旧 yaml 的回退
    dtype_value = dtype_from_str(mcfg.get("dtype") or mcfg["torch_dtype"])

    model = AutoModelForCausalLM.from_pretrained(
        mcfg["name_or_path"],
        quantization_config=bnb_cfg,
        trust_remote_code=mcfg.get("trust_remote_code", True),
        dtype=dtype_value,
        device_map="auto",
        **model_kwargs,
    )
    model.config.use_cache = False                                  # 训练时关闭 KV cache
    if hasattr(model, "generation_config") and model.generation_config is not None:
        model.generation_config.use_cache = False

    # 让 4bit 模型可训练（启用梯度等）
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=cfg["training"].get("gradient_checkpointing", True),
    )

    # ------------------------------------------------------------------ #
    # 3. LoRA 配置                                                         #
    # ------------------------------------------------------------------ #
    lcfg = cfg["lora"]
    peft_config = LoraConfig(
        r=lcfg["r"],
        lora_alpha=lcfg["lora_alpha"],
        lora_dropout=lcfg["lora_dropout"],
        bias=lcfg["bias"],
        task_type=lcfg["task_type"],
        target_modules=lcfg["target_modules"],
    )
    print(f"[LoRA] r={lcfg['r']} alpha={lcfg['lora_alpha']} "
          f"dropout={lcfg['lora_dropout']} targets={lcfg['target_modules']}")

    # ------------------------------------------------------------------ #
    # 4. 数据集（messages 格式由 SFTTrainer 直接消化）                       #
    # ------------------------------------------------------------------ #
    print(f"[数据] 训练集：{train_path}")
    print(f"[数据] 验证集：{val_path}")
    raw = load_dataset(
        "json",
        data_files={"train": str(train_path), "validation": str(val_path)},
    )

    if args.max_train_samples is not None:
        raw["train"] = raw["train"].select(range(min(args.max_train_samples, len(raw["train"]))))
        print(f"[烟测] 训练样本截断为前 {len(raw['train']):,} 条")
    if args.max_eval_samples is not None:
        raw["validation"] = raw["validation"].select(
            range(min(args.max_eval_samples, len(raw["validation"])))
        )
        print(f"[烟测] 验证样本截断为前 {len(raw['validation']):,} 条")

    # ------------------------------------------------------------------ #
    # 5. SFTConfig                                                         #
    # ------------------------------------------------------------------ #
    tcfg = cfg["training"]
    sft_cfg = cfg["sft"]
    output_dir = repo_root / tcfg["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=True)
    logging_dir = repo_root / tcfg.get("logging_dir", "log/Fine_tuning/tensorboard")
    logging_dir.mkdir(parents=True, exist_ok=True)

    # trl 0.16+ 使用 max_length（取代旧 max_seq_length）；同时兼容旧 yaml 键
    max_length_value = sft_cfg.get("max_length") or sft_cfg.get("max_seq_length")

    sft_config_kwargs: dict[str, Any] = dict(
        output_dir=str(output_dir),
        num_train_epochs=tcfg["num_train_epochs"],
        per_device_train_batch_size=tcfg["per_device_train_batch_size"],
        per_device_eval_batch_size=tcfg["per_device_eval_batch_size"],
        gradient_accumulation_steps=tcfg["gradient_accumulation_steps"],
        gradient_checkpointing=tcfg.get("gradient_checkpointing", True),
        # 显式 use_reentrant=False，抑制 PyTorch 2.5+ 的 checkpointing warning
        gradient_checkpointing_kwargs={"use_reentrant": False},
        learning_rate=float(tcfg["learning_rate"]),
        lr_scheduler_type=tcfg["lr_scheduler_type"],
        warmup_ratio=tcfg["warmup_ratio"],
        optim=tcfg["optim"],
        bf16=tcfg.get("bf16", True),
        max_grad_norm=tcfg["max_grad_norm"],
        weight_decay=tcfg["weight_decay"],
        logging_steps=tcfg["logging_steps"],
        logging_dir=str(logging_dir),
        save_steps=tcfg["save_steps"],
        save_total_limit=tcfg["save_total_limit"],
        eval_strategy=tcfg["eval_strategy"],
        eval_steps=tcfg["eval_steps"],
        load_best_model_at_end=tcfg["load_best_model_at_end"],
        metric_for_best_model=tcfg["metric_for_best_model"],
        greater_is_better=tcfg["greater_is_better"],
        report_to=tcfg["report_to"],
        remove_unused_columns=tcfg.get("remove_unused_columns", False),
        dataloader_num_workers=tcfg.get("dataloader_num_workers", 2),
        max_length=max_length_value,
        packing=sft_cfg.get("packing", False),
        max_steps=args.max_steps if args.max_steps is not None else -1,
        seed=seed,
    )
    # 仅当 yaml 明确开启时才传 assistant_only_loss（避免老版 trl 不识别报错）
    if sft_cfg.get("assistant_only_loss"):
        sft_config_kwargs["assistant_only_loss"] = True

    sft_config = SFTConfig(**sft_config_kwargs)

    # ------------------------------------------------------------------ #
    # 6. SwanLab init（如启用）+ SFTTrainer                                 #
    # ------------------------------------------------------------------ #
    maybe_init_swanlab(cfg)

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=raw["train"],
        eval_dataset=raw["validation"],
        peft_config=peft_config,
        processing_class=tokenizer,
    )

    # ------------------------------------------------------------------ #
    # 7. 训练 + 保存                                                        #
    # ------------------------------------------------------------------ #
    print("[启动] 开始训练 ...")
    trainer.train(resume_from_checkpoint=args.resume_from_checkpoint)

    adapter_dir = repo_root / cfg["adapter_dir"]
    adapter_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(adapter_dir))
    # 保存 tokenizer 前还原官方 chat_template，避免把训练用的精简模板写入 adapter/ 目录
    if original_chat_template is not None:
        tokenizer.chat_template = original_chat_template
        print("[ChatTemplate] 已将官方模板还原回 tokenizer（保存到 adapter/ 用）")
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"[完成] LoRA 适配器与 tokenizer 已保存 → {adapter_dir}")

    # 关闭 swanlab run（脚本结尾调用以确保上传完整）
    try:
        import swanlab
        if swanlab.get_run() is not None:
            swanlab.finish()
    except Exception:
        pass


if __name__ == "__main__":
    main()
