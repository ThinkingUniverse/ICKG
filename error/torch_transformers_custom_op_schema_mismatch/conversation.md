# 完整对话记录 · torch / transformers custom_op schema 不兼容

> 时间：2026-05-18
> 参与者：用户 (zhousiyu9875@gmail.com) / Claude (Opus 4.7)

---

## 👤 User

报错：

```
(ickg) root@localhost:~/ICKG# python src/Fine_tuning/training/train_qlora.py \
  --config src/Fine_tuning/configs/train_config.yaml \
  --max-train-samples 50 \
  --max-eval-samples 20 \
  --max-steps 20
Traceback (most recent call last):
  File "/root/ICKG/src/Fine_tuning/training/train_qlora.py", line 63, in <module>
    from peft import LoraConfig, prepare_model_for_kbit_training
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/peft/__init__.py", line 17, in <module>
    from .auto import (
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/peft/auto.py", line 31, in <module>
    from .config import PeftConfig
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/peft/config.py", line 30, in <module>
    from .utils import CONFIG_NAME, PeftType, TaskType
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/peft/utils/__init__.py", line 15, in <module>
    from .constants import ALLOWED_COMPUTE_DTYPES, UPCAST_DTYPES
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/peft/utils/constants.py", line 16, in <module>
    from transformers import BloomPreTrainedModel
  File "<frozen importlib._bootstrap>", line 1075, in _handle_fromlist
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/transformers/utils/import_utils.py", line 2226, in __getattr__
    module = self._get_module(self._class_to_module[name])
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/transformers/utils/import_utils.py", line 2460, in _get_module
    raise e
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/transformers/utils/import_utils.py", line 2458, in _get_module
    return importlib.import_module("." + module_name, self.__name__)
  File "/root/miniconda3/envs/ickg/lib/python3.10/importlib/__init__.py", line 126, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/transformers/models/bloom/modeling_bloom.py", line 26, in <module>
    from ...modeling_layers import GradientCheckpointingLayer
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/transformers/modeling_layers.py", line 27, in <module>
    from .processing_utils import Unpack
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/transformers/processing_utils.py", line 79, in <module>
    from .modeling_utils import PreTrainedAudioTokenizerBase
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/transformers/modeling_utils.py", line 69, in <module>
    from .integrations.finegrained_fp8 import ALL_FP8_EXPERTS_FUNCTIONS
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/transformers/integrations/finegrained_fp8.py", line 30, in <module>
    from .moe import ExpertsInterface, use_experts_implementation
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/transformers/integrations/moe.py", line 250, in <module>
    torch.library.custom_op("transformers::grouped_mm_fallback", _grouped_mm_fallback, mutates_args=())
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/torch/_library/custom_ops.py", line 142, in custom_op
    return inner(fn)
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/torch/_library/custom_ops.py", line 119, in inner
    schema_str = torch._custom_op.impl.infer_schema(fn, mutates_args)
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/torch/_library/infer_schema.py", line 42, in infer_schema
    error_fn(
  File "/root/miniconda3/envs/ickg/lib/python3.10/site-packages/torch/_library/infer_schema.py", line 21, in error_fn
    raise ValueError(
ValueError: infer_schema(func): Parameter input has unsupported type torch.Tensor. The valid types are: dict_keys([<class 'torch.Tensor'>, typing.Optional[torch.Tensor], typing.Sequence[torch.Tensor], typing.List[torch.Tensor], typing.Sequence[typing.Optional[torch.Tensor]], typing.List[typing.Optional[torch.Tensor]], <class 'int'>, typing.Optional[int], typing.Sequence[int], typing.List[int], typing.Optional[typing.Sequence[int]], typing.Optional[typing.List[int]], <class 'float'>, typing.Optional[float], typing.Sequence[float], typing.List[float], typing.Optional[typing.Sequence[float]], typing.Optional[typing.List[float]], <class 'bool'>, typing.Optional[bool], typing.Sequence[bool], typing.List[bool], typing.Optional[typing.Sequence[bool]], typing.Optional[typing.List[bool]], <class 'str'>, typing.Optional[str], typing.Union[int, float, bool], typing.Union[int, float, bool, NoneType], typing.Sequence[typing.Union[int, float, bool]], typing.List[typing.Union[int, float, bool]], <class 'torch.dtype'>, typing.Optional[torch.dtype], <class 'torch.device'>, typing.Optional[torch.device]]). Got func with signature (input: 'torch.Tensor', weight: 'torch.Tensor', offs: 'torch.Tensor') -> 'torch.Tensor')
```

---

## 🤖 Assistant（第一轮：定位根因 + 三种修复方案）

这是 `transformers` 与 `torch` 版本不兼容导致的错误。新版 `transformers` 在 `integrations/moe.py` 中使用了字符串形式的类型注解（`'torch.Tensor'`）调用 `torch.library.custom_op`，但当前 `torch` 版本的 `infer_schema` 无法解析字符串形式的注解，只能识别真实的 `torch.Tensor` 类型。

先看一下当前环境的版本情况。

请你在服务器上先跑一下版本检查：

```bash
conda activate ickg
python -c "import torch, transformers, peft, accelerate, bitsandbytes; \
print('torch:', torch.__version__); \
print('transformers:', transformers.__version__); \
print('peft:', peft.__version__); \
print('accelerate:', accelerate.__version__); \
print('bitsandbytes:', bitsandbytes.__version__)"
```

### 原因分析

报错位置在 `transformers/integrations/moe.py:250`：

```python
torch.library.custom_op("transformers::grouped_mm_fallback", _grouped_mm_fallback, mutates_args=())
```

被注册的函数签名是 `(input: 'torch.Tensor', weight: 'torch.Tensor', offs: 'torch.Tensor')`，注意类型是**字符串形式的 `'torch.Tensor'`**（PEP 563 / `from __future__ import annotations` 的延迟求值）。

而你装的 `torch` 的 `torch._library.infer_schema` 还不支持字符串形式注解 —— 它在白名单里只找 `torch.Tensor` 类对象，找不到字符串 `'torch.Tensor'`，所以抛 `ValueError: Parameter input has unsupported type torch.Tensor`。

**对字符串注解的支持是在 `torch >= 2.5` 才修好的**（PyTorch PR #134985 等改动）。如果你的 `torch` 是 2.3 / 2.4，搭配最新的 `transformers`（4.46+，尤其加了 MoE/FP8 集成的那批）就会炸。

### 推荐修复（按优先级）

**方案 A（推荐）：升级 torch 到 ≥ 2.5，与新版 transformers 配套**

要先确认你的 CUDA 版本（`nvidia-smi` 里的 CUDA Version），然后选对应 wheel。例如 CUDA 12.1：

```bash
conda activate ickg
pip install --upgrade "torch>=2.5" --index-url https://download.pytorch.org/whl/cu121
```

CUDA 12.4：

```bash
pip install --upgrade "torch>=2.5" --index-url https://download.pytorch.org/whl/cu124
```

升级 torch 后，`bitsandbytes` 一般也要同步升一下：

```bash
pip install -U bitsandbytes
```

**方案 B：把 transformers 降到不带这段 MoE custom_op 的版本**

```bash
pip install "transformers==4.44.2" "peft>=0.11,<0.13" "accelerate>=0.33,<0.35"
```

**方案 C（临时绕过，最不推荐）：跳过那行 custom_op 注册**

只在你急着跑通一次、且不会用到 MoE/FP8 路径时再考虑。可以临时把 `transformers/integrations/moe.py:250` 那行用 `try/except` 包起来。但下次升级会被覆盖，治标不治本。

---

## 👤 User（提供 nvidia-smi 输出）

```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 550.163.01             Driver Version: 550.163.01     CUDA Version: 12.4     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
|=========================================+========================+======================|
|   0  NVIDIA A100-SXM4-80GB          Off |   00000000:01:00.0 Off |                    0 |
| N/A   35C    P0             64W /  400W |       1MiB /  81920MiB |     24%      Default |
+-----------------------------------------+------------------------+----------------------+
```

---

## 🤖 Assistant（第二轮：给出 A100 + CUDA 12.4 的最终命令）

A100 + CUDA 12.4，给你最稳的一条升级路径：

### 推荐：升级 torch 到 2.5+ (cu124 wheel)

```bash
conda activate ickg

# 1. 升级 torch / torchvision / torchaudio 到 cu124 版本
pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 2. 同步升级 bitsandbytes / peft / accelerate，匹配新版 transformers
pip install -U bitsandbytes peft accelerate
```

A100 (SM80) 对 cu124 wheel 完全支持，不需要再装 CUDA toolkit，wheel 自带运行时。

### 升级完验证

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

期望看到 `torch: 2.5.x` 或更高、`cuda: 12.4`、`cuda available: True`、`GPU: NVIDIA A100-SXM4-80GB`。

### 再跑训练

```bash
python src/Fine_tuning/training/train_qlora.py \
  --config src/Fine_tuning/configs/train_config.yaml \
  --max-train-samples 50 \
  --max-eval-samples 20 \
  --max-steps 20
```

---

## ✅ 最终解决方案（用户采纳）

```bash
# 1. 升级 torch / torchvision / torchaudio 到 cu124 版本
pip install --upgrade torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 2. 同步升级 bitsandbytes / peft / accelerate，匹配新版 transformers
pip install -U bitsandbytes peft accelerate
```
