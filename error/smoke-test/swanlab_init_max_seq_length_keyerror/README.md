# 2026-05-18 · SwanLab 初始化时 `cfg["sft"]["max_seq_length"]` 抛 KeyError

> 排查时间：2026-05-18
> 关键词：`KeyError: 'max_seq_length'` / `maybe_init_swanlab` / `trl 0.16+` / `max_length` 改名 / yaml 键不一致
> 涉及组件：`trl >= 0.16`、`swanlab`、`transformers`、自研脚本 `train_qlora.py`
> 触发脚本：[src/Fine_tuning/training/train_qlora.py](../../src/Fine_tuning/training/train_qlora.py)
> 配置文件：[src/Fine_tuning/configs/train_config.yaml](../../src/Fine_tuning/configs/train_config.yaml)

---

## 1. 错误现象

烟测命令：

```bash
conda activate lckg
python src/Fine_tuning/training/train_qlora.py \
  --config src/Fine_tuning/configs/train_config.yaml \
  --max-train-samples 50 \
  --max-eval-samples 20 \
  --max-steps 20
```

模型已成功加载、LoRA 已配置、数据集已切到烟测样本数，进入 SFTConfig 构造之后报错：

```
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

注意 SFTConfig 已经构造成功（max_length 这条路径走通了），但下一行 `maybe_init_swanlab(cfg)` 里直接把同一个键当作旧名读取，于是炸在 swanlab.init 的 config 字典构造上。

---

## 2. 原因分析

`trl` 在 0.16 版本起把 SFT 训练的序列长度参数从 `max_seq_length` 改名为 `max_length`。本项目的 yaml 已经按新接口写成：

```yaml
# src/Fine_tuning/configs/train_config.yaml
sft:
  max_length: 5120   # 新键名（trl 0.16+）
  # 旧键 max_seq_length 已删除
  ...
```

脚本主流程构造 SFTConfig 时做了**兼容回退**：

```python
# src/Fine_tuning/training/train_qlora.py:288（旧行号）
max_length_value = sft_cfg.get("max_length") or sft_cfg.get("max_seq_length")
```

但 `maybe_init_swanlab(cfg)` 这个分支**漏掉了同样的回退**，依旧硬编码旧键：

```python
# src/Fine_tuning/training/train_qlora.py:156（旧行号）
config={
    ...
    "max_seq_length": cfg["sft"]["max_seq_length"],   # ❌ yaml 已没有这个键
    ...
}
```

字典查不到 `max_seq_length` 时 Python 直接抛 `KeyError`，触发本错误。

时间线：
1. 前一次提交 `db3fe2c feat: 更新微调代码与文档，支持新版本 transformers 和 QLoRA 训练流程` 升级到了 trl 0.16+，主流程做了改名 + 兼容。
2. SwanLab 初始化是配套新加的，写代码时复制了旧的键名变量串。
3. 烟测命令首次触发 swanlab 分支（`report_to: ["tensorboard", "swanlab"]` 且 `swanlab.enabled: true`），暴露问题。

---

## 3. 解决方案（已采用）

在 `maybe_init_swanlab` 里同样做 `max_length → max_seq_length` 的兼容回退，并把上报到 SwanLab 的 config 字段名改成 `max_length`（与 trl 新接口对齐）。

修改 [src/Fine_tuning/training/train_qlora.py](../../src/Fine_tuning/training/train_qlora.py) 中 `maybe_init_swanlab`：

```python
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
        "max_length": max_length_value,   # ✅ 新键名 + 兼容回退
        "lora_r": cfg["lora"]["r"],
        ...
    },
)
```

修改后直接重跑原命令即可，SwanLab dashboard 里也会看到更准确的 `max_length` 字段（之前会是 `max_seq_length`，与代码新接口不一致）。

---

## 4. 备选方案（未采用，供参考）

### 方案 B：在 yaml 同时写双键

```yaml
sft:
  max_length: 5120
  max_seq_length: 5120   # 给老代码兜底
```

不推荐：两个值靠人工同步，未来一定有人改一个忘改另一个。

### 方案 C：用 `cfg["sft"].get("max_seq_length", cfg["sft"]["max_length"])` 内联

不推荐：把同样的回退表达式抄到每个用到的地方，比抽出一个变量更易写错。

---

## 5. 经验教训

1. **库的关键参数改名时，要全文件扫一遍所有读取点**。本次主流程做了兼容回退，但旁路（监控/可视化）代码忘了同步，触发条件又只在 `report_to` 包含 swanlab 时才走到，掩盖了一段时间。
2. **配置键访问优先用 `.get(...) or .get(old_key)` 而不是 `[...]`**，特别是在过渡期的脚本里——KeyError 比拿到 None 更隐蔽，因为它中断更晚。
3. **类似 trl/transformers 这种快速迭代的库**，每次升级都要看 deprecation/removal 列表：本次现场已经有两个 deprecation warning（`warmup_ratio`、`logging_dir`），它们都会在 transformers v5.2 移除，要在那之前清掉。
4. **看 traceback 的层级**：`main → maybe_init_swanlab → swanlab.init config 构造` 全是同一帧栈，错误源是字面量字符串 `"max_seq_length"`——这种 KeyError 直接 grep 字符串就能定位，不需要怀疑 swanlab/trl 本身。

---

## 6. 完整对话记录

完整原始问答见 [conversation.md](conversation.md)。
