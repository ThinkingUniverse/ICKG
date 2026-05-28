# 2026-05-18 · transformers 注册 custom_op 时 torch.infer_schema 不识别字符串注解

> 排查时间：2026-05-18
> 关键词：`torch.library.custom_op` / `infer_schema` / `transformers::grouped_mm_fallback` / `integrations/moe.py` / `from __future__ import annotations`
> 涉及组件：`torch 2.3/2.4`、`transformers 4.46+`（带 MoE / FP8 集成的版本）、`peft`、`bitsandbytes`
> 触发脚本：[src/Fine_tuning/training/train_qlora.py](../../src/Fine_tuning/training/train_qlora.py)

---

## 1. 错误现象

烟测命令：

```bash
conda activate ickg
python src/Fine_tuning/training/train_qlora.py \
  --config src/Fine_tuning/configs/train_config.yaml \
  --max-train-samples 50 \
  --max-eval-samples 20 \
  --max-steps 20
```

完整 traceback：

```
Traceback (most recent call last):
  File "/root/ICKG/src/Fine_tuning/training/train_qlora.py", line 63, in <module>
    from peft import LoraConfig, prepare_model_for_kbit_training
  File ".../peft/__init__.py", line 17, in <module>
    from .auto import (
  File ".../peft/auto.py", line 31, in <module>
    from .config import PeftConfig
  File ".../peft/config.py", line 30, in <module>
    from .utils import CONFIG_NAME, PeftType, TaskType
  File ".../peft/utils/__init__.py", line 15, in <module>
    from .constants import ALLOWED_COMPUTE_DTYPES, UPCAST_DTYPES
  File ".../peft/utils/constants.py", line 16, in <module>
    from transformers import BloomPreTrainedModel
  File ".../transformers/utils/import_utils.py", line 2458, in _get_module
    return importlib.import_module("." + module_name, self.__name__)
  File ".../transformers/models/bloom/modeling_bloom.py", line 26, in <module>
    from ...modeling_layers import GradientCheckpointingLayer
  File ".../transformers/modeling_layers.py", line 27, in <module>
    from .processing_utils import Unpack
  File ".../transformers/processing_utils.py", line 79, in <module>
    from .modeling_utils import PreTrainedAudioTokenizerBase
  File ".../transformers/modeling_utils.py", line 69, in <module>
    from .integrations.finegrained_fp8 import ALL_FP8_EXPERTS_FUNCTIONS
  File ".../transformers/integrations/finegrained_fp8.py", line 30, in <module>
    from .moe import ExpertsInterface, use_experts_implementation
  File ".../transformers/integrations/moe.py", line 250, in <module>
    torch.library.custom_op("transformers::grouped_mm_fallback", _grouped_mm_fallback, mutates_args=())
  File ".../torch/_library/custom_ops.py", line 142, in custom_op
    return inner(fn)
  File ".../torch/_library/custom_ops.py", line 119, in inner
    schema_str = torch._custom_op.impl.infer_schema(fn, mutates_args)
  File ".../torch/_library/infer_schema.py", line 42, in infer_schema
    error_fn(
  File ".../torch/_library/infer_schema.py", line 21, in error_fn
    raise ValueError(
ValueError: infer_schema(func): Parameter input has unsupported type torch.Tensor.
The valid types are: dict_keys([<class 'torch.Tensor'>, typing.Optional[torch.Tensor], ...]).
Got func with signature (input: 'torch.Tensor', weight: 'torch.Tensor', offs: 'torch.Tensor') -> 'torch.Tensor')
```

错误链最末端非常关键：

```
Parameter input has unsupported type torch.Tensor
Got func with signature (input: 'torch.Tensor', ...)
```

注意 `'torch.Tensor'` 是**带引号的字符串**，不是真正的类对象。

---

## 2. 环境信息

```
GPU       : NVIDIA A100-SXM4-80GB
Driver    : 550.163.01
CUDA      : 12.4 (nvidia-smi 显示)
Conda env : ickg (Python 3.10)
报错前 torch : 2.3 / 2.4 系列（不支持字符串形式注解）
transformers : 4.46+（已加入 MoE / FP8 custom_op 注册）
```

---

## 3. 原因分析

报错位置：[transformers/integrations/moe.py:250](#)

```python
torch.library.custom_op(
    "transformers::grouped_mm_fallback",
    _grouped_mm_fallback,
    mutates_args=()
)
```

被注册的 `_grouped_mm_fallback` 函数签名是：

```python
def _grouped_mm_fallback(
    input: 'torch.Tensor',
    weight: 'torch.Tensor',
    offs: 'torch.Tensor',
) -> 'torch.Tensor':
    ...
```

类型注解使用了**字符串形式**（PEP 563 / 文件头的 `from __future__ import annotations` 让注解延迟求值），这是新版 transformers 普遍采用的写法。

而 `torch._library.infer_schema` 在 torch 2.3 / 2.4 里只接受真正的类对象 `torch.Tensor`，不会对字符串 `'torch.Tensor'` 调用 `eval`/`get_type_hints` 解析，于是在白名单查找时直接抛 `ValueError`。

**对字符串注解的支持是 `torch >= 2.5` 才补上的**（PyTorch PR #134985 等改动）。所以：

| torch | transformers (≥4.46) | 结果 |
|---|---|---|
| ≤ 2.4 | 装最新版 | ❌ 本错误 |
| ≥ 2.5 | 装最新版 | ✅ 正常 |
| ≤ 2.4 | 降到 4.44.x（无 MoE 注册） | ✅ 正常 |

---

## 4. 解决方案（最终采用）

A100 + CUDA 12.4 驱动，升级 torch 到 2.5+ 的 cu124 wheel：

```bash
conda activate ickg

# 1. 升级 torch / torchvision / torchaudio 到 cu124 版本
pip install --upgrade torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cu124

# 2. 同步升级 bitsandbytes / peft / accelerate，匹配新版 transformers
pip install -U bitsandbytes peft accelerate
```

A100 (SM80) 对 cu124 wheel 完全支持；wheel 自带运行时，不需要单独装 CUDA toolkit。

### 验证

```bash
python -c "
import torch, transformers, peft, accelerate, bitsandbytes
print('torch:', torch.__version__, '| cuda:', torch.version.cuda, '| cuda available:', torch.cuda.is_available())
print('transformers:', transformers.__version__)
print('peft:', peft.__version__)
print('accelerate:', accelerate.__version__)
print('bitsandbytes:', bitsandbytes.__version__)
print('GPU:', torch.cuda.get_device_name(0))
"
```

期望：`torch: 2.5.x+` / `cuda: 12.4` / `cuda available: True` / `GPU: NVIDIA A100-SXM4-80GB`。

---

## 5. 备选方案（未采用，供参考）

### 方案 B：降 transformers 到不带 MoE custom_op 的版本

如果 torch 被其他代码绑死无法升级：

```bash
pip install "transformers==4.44.2" "peft>=0.11,<0.13" "accelerate>=0.33,<0.35"
```

4.44.x 还没有 `integrations/moe.py` 的 `grouped_mm_fallback` 注册，QLoRA 训练完全够用。

### 方案 C：临时 try/except 包裹注册行（最不推荐）

只在赶时间跑通一次、且确认不会走 MoE / FP8 路径时考虑。把 `transformers/integrations/moe.py:250` 那行 `torch.library.custom_op(...)` 包进 `try/except Exception: pass`。下次 `pip install -U` 会被覆盖，治标不治本。

---

## 6. 经验教训

1. **看 traceback 的最后一行 `Got func with signature`**——`'torch.Tensor'` 带引号是关键证据，直接指向「字符串注解未被解析」这个根因，不要被前面长长的 import 链带偏。
2. **`from peft import ...` 报错≠peft 问题**。peft 只是触发了 transformers 的 lazy import 链，真正的爆点在 transformers 的 `integrations/moe.py`。
3. **库间版本兼容性问题先看版本矩阵**：`torch` ↔ `transformers` ↔ `bitsandbytes` ↔ `peft` ↔ `accelerate` 这五件套要一起升或一起锁。
4. **A100 + cu124 wheel 是当前最稳的搭配**，不要装 cu118 wheel 配 CUDA 12.4 驱动（虽然能跑但 bitsandbytes 容易出 `libbitsandbytes_cudaXXX.so` 找不到的二次故障）。

---

## 7. 完整对话记录

完整原始问答见 [conversation.md](conversation.md)。
