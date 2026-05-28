# 2026-05-18 · TRL SFTTrainer 拒绝 Baichuan-M2-32B chat template

> 排查时间：2026-05-18
> 关键词：`assistant_only_loss` / `get_training_chat_template` / `prefix-preservation` / `{% generation %}`
> 涉及组件：`trl 0.16+`, `transformers`, `Baichuan-M2-32B`（Qwen3-style chat template）
> 修复产物：[src/Fine_tuning/training/baichuan_m2_training_template.jinja](../../src/Fine_tuning/training/baichuan_m2_training_template.jinja)、[src/Fine_tuning/training/train_qlora.py](../../src/Fine_tuning/training/train_qlora.py)
> 原始痕迹（按时间顺序）：[01](01_original_error.txt) → [02](02_chat_template_dump.txt) → [03](03_test_round1_inline_bytes_and_mask.txt) → [04](04_test_round2_trl_source_dump.txt) → [05](05_test_round3_real_samples.txt) → [06](06_diagnostics_helpers_check.txt)

---

## 1. 错误现象

烟测命令：

```bash
python src/Fine_tuning/training/train_qlora.py \
  --config src/Fine_tuning/configs/train_config.yaml \
  --max-train-samples 50 --max-eval-samples 20 --max-steps 20
```

加载模型、LoRA、数据集都成功，SwanLab 也初始化完毕，但在实例化 `SFTTrainer` 时崩掉：

```
File ".../trl/trainer/sft_trainer.py", line 1194, in __init__
    self.chat_template = get_training_chat_template(processing_class)
File ".../trl/chat_template_utils.py", line 688, in get_training_chat_template
    raise ValueError(
The chat template is not training-compatible (missing prefix-preservation
or `{% generation %}` markers) and patching is not supported for this template.
Please manually modify the chat template for training.
```

---

## 2. 根因分析

`train_config.yaml` 里启用了：

```yaml
sft:
  assistant_only_loss: true   # 仅对 assistant 输出 token 计算 loss
```

trl 0.16+ 看到这个标志后会调用 `get_training_chat_template(processing_class)`，源码核心逻辑（来自 `trl/chat_template_utils.py`）：

```python
prefix_ok = (
    not supports_tool_calling(processing_class)
    or is_chat_template_prefix_preserving(processing_class)
)
if prefix_ok and "{% generation %}" in processing_class.chat_template:
    return None  # 模板已经合规，无需 patch

# 否则尝试匹配已知模板（Cohere / Gemma / Qwen2.5 / Qwen3 / GLM-4 / Llama3 / Phi3 / GPT-OSS / DeepSeek-V3 …）
# 都不匹配则 raise
```

**两个 gate 必须同时通过**：

| Gate | 判定 | Baichuan-M2 自带模板的情况 |
|---|---|---|
| ① 字面 substring `"{% generation %}"` 出现在 chat_template 里 | 字符串包含检查 | ❌ 缺失 |
| ② `prefix_ok` 为 True：要么不支持 tool calling，要么模板前缀保留 | 模板渲染 `messages[:k]` 必须是 `messages[:k+1]` 的前缀 | ❌ 因为有 `ns.last_query_index` 反向扫描逻辑，**最后一轮 assistant 会被包成 `<think>\n…\n</think>\n\n`**，前面的不会，前缀不保留 |

Baichuan-M2 没在 trl 的已知模板白名单里 → 报错。

### 2.1 官方模板里破坏前缀保留的那段

```jinja
{%- set ns = namespace(multi_step_tool=true, last_query_index=messages|length - 1) %}
{%- for message in messages[::-1] %}
    {%- set index = (messages|length - 1) - loop.index0 %}
    {%- if ns.multi_step_tool and message.role == "user" and not(...) %}
        {%- set ns.last_query_index = index %}
    {%- endif %}
{%- endfor %}

{%- for message in messages %}
    {%- elif message.role == "assistant" %}
        {%- if loop.index0 > ns.last_query_index %}
            {# 「最后一轮 assistant」分支：插入 <think>\n…\n</think>\n\n #}
        {%- else %}
            {# 「中间 assistant」分支：直接发 content #}
        {%- endif %}
```

`last_query_index` 取决于"整个 messages 序列里最靠后的 user"的位置，因此渲染同一条 assistant 时，**结果会随着后续是否还有 user 消息而改变** —— 这正是非前缀保留。

---

## 3. 修复方案：训练期切换到简化模板，保存前还原官方模板

### 3.1 数据观察

[data/Fine_tuning_dataset/training_ready/v1/train.jsonl](../data/Fine_tuning_dataset/training_ready/v1/train.jsonl) 的格式是干净的 `[system, user, assistant]` 三件套，assistant 输出直接是 JSON triple 数组：

- 没有 `<think>` 标签
- 没有 tools
- 没有 tool_calls

这意味着 Baichuan-M2 官方模板里的 tools / last_query_index / reasoning_content 三段逻辑对训练数据都是"空跑"。可以安全去掉。

### 3.2 简化版训练模板

新建 [src/Fine_tuning/training/baichuan_m2_training_template.jinja](../src/Fine_tuning/training/baichuan_m2_training_template.jinja)：

```jinja
{%- if messages[0].role == 'system' %}
    {{- '<|im_start|>system\n' + messages[0].content + '<|im_end|>\n' }}
{%- endif %}
{%- for message in messages %}
    {%- if (message.role == "user") or (message.role == "system" and not loop.first) %}
        {{- '<|im_start|>' + message.role + '\n' + message.content + '<|im_end|>\n' }}
    {%- elif message.role == "assistant" %}
        {{- '<|im_start|>' + message.role + '\n' -}}
        {% generation %}
        {{- message.content + '<|im_end|>\n' -}}
        {% endgeneration %}
    {%- endif %}
{%- endfor %}
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
{%- endif %}
```

设计要点：

1. **删掉 `tools` 分支** → trl 的 `supports_tool_calling()` 返回 False → `prefix_ok` 自动 True，第二关绕过。
2. **删掉 `ns.last_query_index` 反向扫描和 think-wrapping 分支** → 每条 assistant 都直接发 `content`，模板真·前缀保留（对所有 message 序列都成立）。
3. **删掉 `tool_calls` 渲染和 `reasoning_content` 字段处理** —— 训练数据用不上。
4. **`{% generation %}` 用字面形式**（不能写成 `{%- generation %}`），因为 trl 用的是字符串包含检测；外层 `-}}` 负责吃掉换行+缩进保证 byte-equal。
5. **`<|im_end|>\n` 包在 `{% generation %}` 内**，让模型学会自己输出停止 token。

对当前训练数据，简化模板与官方模板渲染结果**字节完全一致**（验证过 3 条真实样本）。

### 3.3 train_qlora.py 加载/还原逻辑

[src/Fine_tuning/training/train_qlora.py](../src/Fine_tuning/training/train_qlora.py) 关键改动两处：

**(a) tokenizer 加载之后、SFTTrainer 构造之前**，切换模板并备份原版：

```python
original_chat_template: str | None = None
if cfg.get("sft", {}).get("assistant_only_loss"):
    tpl_path = Path(__file__).resolve().parent / "baichuan_m2_training_template.jinja"
    if tpl_path.exists():
        original_chat_template = tokenizer.chat_template          # 备份官方模板
        tokenizer.chat_template = tpl_path.read_text(encoding="utf-8")
        print(f"[ChatTemplate] 训练期间已切换到简化模板：{tpl_path.name}（保存前会还原为官方模板）")
    else:
        sys.exit(f"[错误] assistant_only_loss=True 但未找到训练用 chat_template：{tpl_path}")
```

**(b) 保存 adapter 前还原**，避免把训练用的精简模板写进 `adapter/` 目录：

```python
trainer.save_model(str(adapter_dir))
if original_chat_template is not None:
    tokenizer.chat_template = original_chat_template
    print("[ChatTemplate] 已将官方模板还原回 tokenizer（保存到 adapter/ 用）")
tokenizer.save_pretrained(str(adapter_dir))
```

这样保存下来的 `adapter/` 目录里的 tokenizer 与 base 模型字节一致；推理服务（vllm / TGI / HF inference）按官方 chat template 工作，不受训练期 patch 影响。

---

## 4. 验证流程（按时间顺序）

### 4.0 原始报错与模板 dump

- [01_original_error.txt](01_original_error.txt) — 烟测命令完整 bash 输出，结尾是 trl 抛的 `ValueError`。
- [02_chat_template_dump.txt](02_chat_template_dump.txt) — Baichuan-M2-32B 官方 `tokenizer.chat_template` 原文 + special / added tokens 清单（Qwen3-style，带 thinking_mode / tools / tool_calls 三段逻辑）。

### 4.1 第一次试验（失败）

文件：[03_test_round1_inline_bytes_and_mask.txt](03_test_round1_inline_bytes_and_mask.txt)

当时模板用的是 `{%- generation %}`（带 `-` 去空白标记），且保留了官方的 tools/last_query_index 全部逻辑。

| 检查 | 结果 |
|---|---|
| `bytes equal?` | ✅ True |
| `trl check` | ❌ FAILED |
| assistant_masks | ✅ 正确（23 个 assistant token 被标记） |

**结论**：Jinja 层面 `{%- generation %}` 已被识别，transformers 的 `AssistantTracker` 正确生成 mask；但 trl 用的是**字面字符串检查** `"{% generation %}" in chat_template`，`{%-` 形式不匹配。

修复：把 `{%- generation %}` 改成 `{% generation %}`，并用 `-}}` / `{{-` 控制周围空白。

### 4.2 第二次试验（仍失败，附 trl 源码 dump）

文件：[04_test_round2_trl_source_dump.txt](04_test_round2_trl_source_dump.txt)

把 `{%- generation %}` 改成字面 `{% generation %}` 后再测，并加 dump trl 源码以确认它到底在检查什么。

| 检查 | 结果 |
|---|---|
| `bytes equal?` | ✅ True |
| `trl check` | ❌ FAILED |
| `get_training_chat_template` 源码 | 已 dump 出来，关键判定见第 2 节 |

dump 揭示了 trl 真正有两道 gate：substring 检查 + `prefix_ok`（依赖 `supports_tool_calling` 与 `is_chat_template_prefix_preserving`）。Baichuan-M2 的官方模板 prefix 不保留（`last_query_index` 反向扫描那段），所以即便加上 `{% generation %}` 也过不了第二关。

### 4.3 第三次试验（用真实训练样本，仍失败 —— 服务器版本未同步）

文件：[05_test_round3_real_samples.txt](05_test_round3_real_samples.txt)

| 检查 | 结果 |
|---|---|
| `3 samples bytes equal?` | ✅ True |
| `trl check` | ❌ FAILED |
| `sample#0 assistant_in_loss` | 742 token，从 `<think>\n\n</think>\n\n[{"head":...` 到 `<|im_end|>` |

输出里 assistant token 开头出现 `<think>\n\n</think>\n\n`（这是官方模板 `last_query_index` 分支的产物），说明此时**服务器上跑的还是没去掉 tools 的旧版**，简化模板的 Write 改动还没同步到远端。

经验：远端跑代码、本地写代码的协作模式下，每次本地改完务必先确认推送/同步，再在远端测试。

### 4.4 helper 函数 dump（定位真凶）

文件：[06_diagnostics_helpers_check.txt](06_diagnostics_helpers_check.txt)

读 trl 源码后确认两个 helper 的逻辑：

- **`supports_tool_calling(tok)`**：用一组带 sentinel 的 `[user → assistant(tool_calls) → tool]` 消息渲染，检查所有 sentinel 是否出现在输出里。模板里有 tools 分支才会 True。
- **`is_chat_template_prefix_preserving(tok)`**：渲染 `messages1=[user, assistant_with_tool_calls]` 和 `messages2=messages1+[tool, …, add_generation_prompt=True]`，要求 `ids2[:len(ids1)] == ids1`。

切换到简化模板后再测：

```
'{% generation %}' in chat_template: True
supports_tool_calling(tok):           False
is_chat_template_prefix_preserving(tok): True
```

三关全部通过 → `get_training_chat_template` 返回 None（模板原样可用）→ SFTTrainer 能正常初始化。

---

## 5. 关键经验

### 5.1 trl 的两道检查机制

`assistant_only_loss=True` 触发的检查不仅看 `{% generation %}` 标记，还要求模板**前缀保留**。任何"最后一轮做特殊处理"的模板（典型如 Qwen3 / Baichuan-M2 的 think-wrapping、某些模型的 system-prompt 注入逻辑）都过不了这关。

绕过办法：要么**让模板真前缀保留**（去掉位置敏感的逻辑），要么**让 `supports_tool_calling` 返回 False**（删 tools 分支）。后者通常更省事。

### 5.2 `{% generation %}` 的字面性

trl 用的是 `"{% generation %}" in chat_template` 这种字面 substring 检查 —— 不接受 `{%- generation %}` / `{%generation%}` / `{% generation -%}` 这些等价写法。要在保持渲染 byte-equal 的同时通过这关，得：

```jinja
{{- '...prefix...' -}}              {# -}} 吃掉源文件里到下一行的换行+缩进 #}
{% generation %}                    {# 必须字面这样写 #}
    {{- 'content' -}}
{% endgeneration %}                 {# 同样要字面 #}
```

而不是用 `{%- generation %}` 让 Jinja 自己 strip。

### 5.3 训练模板 vs 推理模板

为了训练去掉 tools/think 等逻辑后，**别把精简模板写进 adapter 目录** —— 否则下游推理服务拿到的 tokenizer 会和 base 模型不一致。正确做法：训练前覆盖、保存前还原（本次修复采用此方案）。

### 5.4 transformers 的 `{% generation %}` 扩展是 no-op 渲染

`{% generation %}` 由 transformers 注册的 `AssistantTracker` 扩展实现，**只记录字符 offset，不改变输出**。因此带 mark 的模板与不带 mark 的模板渲染结果完全一致，可以放心 byte-equal 比对。

### 5.5 服务器/本地文件同步坑

本次第二次试验之所以失败，根因是**远端服务器上的模板文件没有更新到最新的简化版本**。涉及远端跑代码、本地写代码的场景，每次本地改完务必先确认 push/同步到服务器，再在服务器上跑测试，否则一直在调旧版本，浪费时间。

---

## 6. 复现路径速查

如果以后碰到类似 "chat template is not training-compatible" 报错：

1. 看 trl 报错堆栈，定位到 `get_training_chat_template` 这一行。
2. dump tokenizer.chat_template 看是否有 `{% generation %}`（字面、无 `-`）。
3. 跑下面这段一次性诊断脚本（输出 3 个 bool）：

```python
from transformers import AutoTokenizer
import trl.chat_template_utils as m
tok = AutoTokenizer.from_pretrained("<your-model>", trust_remote_code=True)
# 如果用了自定义模板：tok.chat_template = open("your.jinja").read()
print("substring:", "{% generation %}" in tok.chat_template)
print("supports_tool_calling:", m.supports_tool_calling(tok))
print("is_prefix_preserving: ", m.is_chat_template_prefix_preserving(tok))
```

判定：

- `substring=False` → 改模板，把 `<|im_start|>assistant\n` 之后的 body 包进 `{% generation %} ... {% endgeneration %}`。
- `supports_tool_calling=True` 且 `is_prefix_preserving=False` → 要么删 tools 分支，要么让所有 assistant 渲染分支统一（不要按消息位置分支）。
- 两条都满足后，`get_training_chat_template` 会返回 None，训练可继续。

---

## 7. 相关文件

### 7.1 代码 / 配置

| 文件 | 作用 |
|---|---|
| [src/Fine_tuning/training/train_qlora.py](../../src/Fine_tuning/training/train_qlora.py) | 训练主脚本，新增模板切换/还原逻辑 |
| [src/Fine_tuning/training/baichuan_m2_training_template.jinja](../../src/Fine_tuning/training/baichuan_m2_training_template.jinja) | 训练专用简化模板 |
| [src/Fine_tuning/configs/train_config.yaml](../../src/Fine_tuning/configs/train_config.yaml) | `sft.assistant_only_loss: true` 触发了本次检查 |

### 7.2 排查痕迹（本目录内）

| 文件 | 作用 |
|---|---|
| [01_original_error.txt](01_original_error.txt) | 烟测命令的原始 bash 报错输出（`ValueError: ... not training-compatible ...`） |
| [02_chat_template_dump.txt](02_chat_template_dump.txt) | Baichuan-M2-32B 自带 `tokenizer.chat_template` 原文 + special/added tokens 清单 |
| [03_test_round1_inline_bytes_and_mask.txt](03_test_round1_inline_bytes_and_mask.txt) | 第一次内联测试：`{%- generation %}` 形式 → bytes equal True / trl FAILED / mask 正确 |
| [04_test_round2_trl_source_dump.txt](04_test_round2_trl_source_dump.txt) | 第二次测试 + trl `get_training_chat_template` 源码 dump（揭示 `prefix_ok` 这道 gate） |
| [05_test_round3_real_samples.txt](05_test_round3_real_samples.txt) | 第三次测试：用真实训练样本，仍 FAILED（实为服务器版本未同步导致跑的还是旧模板） |
| [06_diagnostics_helpers_check.txt](06_diagnostics_helpers_check.txt) | `supports_tool_calling` / `is_chat_template_prefix_preserving` 源码 + 简化模板上三关全绿 |
