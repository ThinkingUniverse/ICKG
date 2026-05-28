# 完整对话记录 · SwanLab 初始化 KeyError: 'max_seq_length'

> 时间：2026-05-18
> 参与者：用户 (zhousiyu9875@gmail.com) / Claude (Opus 4.7)

---

## 👤 User

远程服务器报 `KeyError: 'max_seq_length'`：

```
(ickg) root@localhost:~/ICKG# python src/Fine_tuning/training/train_qlora.py \
  --config src/Fine_tuning/configs/train_config.yaml \
  --max-train-samples 50 \
  --max-eval-samples 20 \
  --max-steps 20
[量化] {'load_in_4bit': True, 'bnb_4bit_quant_type': 'nf4', 'bnb_4bit_use_double_quant': True, 'bnb_4bit_compute_dtype': 'bfloat16'}
[模型] 加载 /root/ICKG/models/hf/Baichuan-M2-32B ...
Loading weights: 100%|...| 771/771 [01:09<00:00, 11.06it/s]
[LoRA] r=16 alpha=32 dropout=0.05 targets=['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']
[数据] 训练集：/root/ICKG/data/Fine_tuning_dataset/training_ready/v1/train.jsonl
[数据] 验证集：/root/ICKG/data/Fine_tuning_dataset/training_ready/v1/val.jsonl
Generating train split: 4500 examples [00:00, 9120.78 examples/s]
Generating validation split: 250 examples [00:00, 8457.76 examples/s]
[烟测] 训练样本截断为前 50 条
[烟测] 验证样本截断为前 20 条
[transformers] warmup_ratio is deprecated and will be removed in v5.2. Use `warmup_steps` instead.
[transformers] `logging_dir` is deprecated and will be removed in v5.2. Please set `TENSORBOARD_LOGGING_DIR` instead.
Traceback (most recent call last):
  File "/root/ICKG/src/Fine_tuning/training/train_qlora.py", line 365, in <module>
    main()
  File "/root/ICKG/src/Fine_tuning/training/train_qlora.py", line 332, in main
    maybe_init_swanlab(cfg)
  File "/root/ICKG/src/Fine_tuning/training/train_qlora.py", line 156, in maybe_init_swanlab
    "max_seq_length": cfg["sft"]["max_seq_length"],
KeyError: 'max_seq_length'
```

IDE 选中行：[src/Fine_tuning/training/train_qlora.py:156](../../src/Fine_tuning/training/train_qlora.py#L156)，光标在 `max_seq_length`。

---

## 🤖 Assistant

读了 [src/Fine_tuning/training/train_qlora.py](../../src/Fine_tuning/training/train_qlora.py) 与 [src/Fine_tuning/configs/train_config.yaml](../../src/Fine_tuning/configs/train_config.yaml) 之后确认：

- yaml 已经按 trl 0.16+ 新接口写成 `sft.max_length: 5120`，没有 `max_seq_length` 这个键。
- 脚本主流程 [train_qlora.py:288](../../src/Fine_tuning/training/train_qlora.py#L288) 已经做过兼容回退：
  ```python
  max_length_value = sft_cfg.get("max_length") or sft_cfg.get("max_seq_length")
  ```
- 但 `maybe_init_swanlab` 这条分支漏改，依旧硬读 `cfg["sft"]["max_seq_length"]`，触发本错误。

### 修复

把同样的回退搬到 `maybe_init_swanlab`，并把 SwanLab config 字段名也改成 `max_length`：

```python
def maybe_init_swanlab(cfg: dict) -> None:
    ...
    # trl 0.16+ 用 max_length（取代旧 max_seq_length），这里同样做兼容回退
    sft_block = cfg.get("sft", {})
    max_length_value = sft_block.get("max_length") or sft_block.get("max_seq_length")

    swanlab.init(
        project=sw_cfg.get("project", "ICKG"),
        workspace=sw_cfg.get("workspace"),
        experiment_name=sw_cfg.get("experiment_name"),
        description=sw_cfg.get("description"),
        mode=sw_cfg.get("mode", "cloud"),
        config={
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
```

### 复测

重新执行原烟测命令：

```bash
conda activate lckg
python src/Fine_tuning/training/train_qlora.py \
  --config src/Fine_tuning/configs/train_config.yaml \
  --max-train-samples 50 \
  --max-eval-samples 20 \
  --max-steps 20
```

应通过 `[SwanLab] 已初始化 ...` 这一行，开始 SFTTrainer 训练。

---

## 🤖 Assistant（后续整理）

应用户要求，把本次完整对话整理成 markdown 归档，目录结构对齐既有的 `error/torch_transformers_custom_op_schema_mismatch/`：

- [error/swanlab_init_max_seq_length_keyerror/README.md](README.md) —— 错误概述、原因分析、解决方案与经验教训
- [error/swanlab_init_max_seq_length_keyerror/conversation.md](conversation.md) —— 本文件，原始对话留档

便于以后再次在新脚本/新键名过渡场景中遇到类似 KeyError 时直接对照。
