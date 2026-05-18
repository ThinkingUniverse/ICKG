# 基于大语言模型构建免疫细胞知识图谱 — 微调阶段汇报

> 用途：本文档作为 PPT 制作的内容底稿，覆盖从数据处理到 QLoRA 微调与合并的完整流程。每个一级标题对应 1 张幻灯片，二级标题对应该页内的 bullet 块或子图。
> 日期：2026-05-15

---

## 1. 项目目标与整体路线

### 背景
- 关键词「免疫细胞」在 PubMed 上爬取近 10 年共 **752,078 篇摘要**
- 用百川 M3 API + 自写提示词从摘要中抽取**知识三元组**（用于构建免疫细胞知识图谱）
- API 抽取成本高、速度慢，无法覆盖全部 75 万篇

### 解决方案
- 把 API 已抽取的高质量三元组作为训练集
- 用 **QLoRA 微调 Baichuan-M2-32B**，使本地模型按相同标准抽取剩余 68 万篇摘要
- 微调后**推理成本 → 0 API 调用**，速度可控、可重复

### 整体流程
```
PubMed 摘要 (75 万)
      │
      ├─→ API 抽取 (Baichuan M3) ── 72.4 万条三元组 (两批，已清洗)
      │           │
      │           └─ 第二批 (v2 prompt, 30 万条) ── 作为本期训练数据来源
      │
      └─→ QLoRA 微调 Baichuan-M2-32B
                  │
                  └─→ 本地推理抽取剩余 68 万篇 (下一期)
```

---

## 2. 已有数据：两批 API 抽取结果

| 批次 | 提示词版本 | 涵盖关系数 | 涉及摘要数 | 三元组总数 |
|---|---|---:|---:|---:|
| 第一批 | v1 | 25 | ~4 万 | **423,823** |
| 第二批 | v2 | 89 | ~3 万（与第一批无重叠） | **300,931** |

- 两批都经过 4 阶段清洗：**ID 添加 → 格式校验 → 实体类型校验 → 关系类型校验**
- 微调目标按 v2 提示词标准抽取，故**仅用第二批**作为训练源

---

## 3. 训练数据构造（5 步流水线）

### Pipeline 总览

```
01_build_pmid_index.py        →  pmid_to_abstract.jsonl       (752,078)
02_aggregate_by_pmid.py       →  pmid_to_triples.jsonl        (27,862 PMID / 300,931 三元组)
03_stratified_sampling.py     →  sampled_5000_pmids.txt       (5,000 PMID)
04_build_sft_dataset.py       →  sft_dataset.jsonl            (5,000 条 messages 样本)
05_split_train_val_test.py    →  train.jsonl / val.jsonl / test.jsonl   (4500/250/250)
```

每个脚本均：双语 header、`argparse` 中文 help、所有阈值从 `data_config.yaml` 读取（不写死）。

---

## 4. 分层采样策略（关键创新点）

### 为什么不能随机采

如果直接随机抽 5000 篇：
- **关系长尾被吃掉**：复制 / 切片 / 蛋白磷酸化等低频关系可能在 5000 中出现 0 次 → 模型完全不会
- **某些过度热门关系 over-represent**：v2 提示词中 `increases` 异常高于 `associated_with`（不符合"associated_with 应是兜底关系最常用"的直觉）→ 模型偏置

### 分层采样规则（写在 `data_config.yaml`）

#### A. 三元组数分桶（控制摘要复杂度分布）
| 桶 | 三元组数 | 占比 | 数量 |
|---|---|---:|---:|
| A | 3-7 条 | 40% | 2000 |
| B | 8-15 条 | 40% | 2000 |
| C | ≥16 条（截断到 30） | 20% | 1000 |
| 0 | <3 条 | 排除 | — |

#### B. 关系覆盖保证
- 87 种关系（已合并 U/反U 到 associated_with）
- 目标：每种关系出现在 ≥ 50 个 PMID 中
- 实测：81 种达成 ≥ 50；剩 6 种（complements 36、competes_with 35…）受数据本身限制，**含它们的所有 PMID 几乎都被纳入**

#### C. 关系再平衡（修正长尾偏置）
- **降采样**：含 `increases` 的 PMID 占比 ≤ 30%
- **过采样**：含 `associated_with` 的 PMID 占比 ≥ 35%
- 实测：increases **30.00%** ✅  /  associated_with **51.44%** ✅

#### D. 4-pass 采样算法
1. Pass A：低频关系强制覆盖（按反向索引）
2. Pass B：满足 min_share 下限
3. Pass C：剩余配额随机填，遵守 max_share 上限
4. Pass D：兜底回填（放宽 max_share）

---

## 5. 训练样本格式（messages 标准）

每条样本是 OpenAI messages 格式（SFTTrainer 原生支持）：

```json
{
  "PMID": "12345678",
  "messages": [
    {"role": "system",    "content": "<精简版 Triple_prompt_v2_finetune.md 全文>"},
    {"role": "user",      "content": "<title + 空格 + abstract，连续空白压成单空格>"},
    {"role": "assistant", "content": "<JSON 数组，所有三元组>"}
  ]
}
```

### 关键设计选择
| 项 | 选择 | 理由 |
|---|---|---|
| 提示词 | **精简版**（实测 1,919 tokens） | 完整 v2 提示词 ~2000+ tokens 包含大量示例；精简版只保留 schema 与输出格式，由 5000 个样本隐式学规则 |
| user 内容 | title + abstract 合并 | 与原 API 调用 `Triple_extraction.py` 完全一致，确保训练与未来推理输入域对齐 |
| assistant 内容 | 紧凑 JSON（`separators=(",", ":")`） | 省 token；剔除 ID1/ID2/PMID 字段（推理不需要） |
| score 过滤 | **不过滤** | 保留全部三元组，让模型学会输出 score，低分样本提供边界感 |
| Loss 计算范围 | `assistant_only_loss=True` | TRL 0.16+ 特性：只在 assistant 输出 token 上计算 loss，user 摘要不参与梯度 |

### token 长度实测（Qwen2.5 tokenizer，500 条样本）
| 字段 | min | median | p95 | max |
|---|---:|---:|---:|---:|
| system | 1919 | 1919 | 1919 | 1919 |
| user | 62 | 369 | 637 | 907 |
| assistant | 174 | 668 | 1573 | 3078 |
| **total** | **2171** | **2994** | **3949** | **5648** |

→ `max_length=5120` 覆盖 99% 样本

---

## 6. 模型与训练框架选型

### 微调对象：Baichuan-M2-32B
- 32B 参数，bf16 ≈ 65 GB
- Baichuan-M2 系列对中文医学文献领域表现优异

### 为什么不用其他变体？
| 变体 | 用途 | 能否用于训练 |
|---|---|---|
| Baichuan-M2-32B（bf16） | 训练 + 推理基座 | ✅ **本期使用** |
| Baichuan-M2-32B-GPTQ-Int4 | 推理加速（vLLM/TGI） | ❌ 已 GPTQ 量化，梯度链断开 |
| Baichuan-M2-32B-Q4_K_M-GGUF | llama.cpp/ollama 部署 | ❌ 部署格式，无计算图 |

### 训练框架：PEFT + BitsAndBytes（QLoRA）+ TRL SFTTrainer
- **PEFT**：HuggingFace 官方 PEFT 库，与任意 HF 模型兼容
- **BitsAndBytes 4bit**：load 时把 bf16 权重动态量化到 4bit nf4，base 显存从 65 GB → 18 GB
- **TRL SFTTrainer**：HF 官方监督微调封装，原生支持 messages 格式 + LoRA
- **不选 Unsloth**：Baichuan-M2-32B 是新模型，Unsloth 优化支持未确认
- **不用 DeepSpeed**：单卡 A100 80GB + QLoRA 完全够用

---

## 7. 训练超参（写在 train_config.yaml）

### 量化（BitsAndBytesConfig）
- `load_in_4bit=True`
- `bnb_4bit_quant_type="nf4"` （NormalFloat4，QLoRA 论文推荐）
- `bnb_4bit_use_double_quant=True` （二次量化，再省 ~10% 显存）
- `bnb_4bit_compute_dtype=bfloat16` （前向反量化后用 bf16 计算）

### LoRA（LoraConfig）
| 参数 | 值 | 说明 |
|---|---|---|
| r | 16 | 秩；可学参数维度 |
| lora_alpha | 32 | 缩放，alpha/r = 2 |
| lora_dropout | 0.05 | LoRA 层 dropout |
| target_modules | `q,k,v,o,gate,up,down_proj` | 7 个线性层（注意力 4 + MLP 3） |
| task_type | `CAUSAL_LM` | 因果语言建模 |

### 训练（SFTConfig，TRL 0.16+ 新 API）
| 参数 | 值 | A100 80GB 优化点 |
|---|---|---|
| num_train_epochs | 3 | |
| per_device_train_batch_size | **2** | 从 1 提到 2，吞吐 ~2× |
| gradient_accumulation_steps | **8** | 保持有效 batch=16 |
| gradient_checkpointing | True | 用计算换显存 |
| `gradient_checkpointing_kwargs.use_reentrant` | False | 抑制 PyTorch 2.5+ warning |
| learning_rate | 1e-4 | QLoRA 常用范围 1e-4 ~ 2e-4 |
| lr_scheduler_type | cosine | |
| warmup_ratio | 0.03 | |
| optim | `paged_adamw_8bit` | 分页 8bit 优化器，省 host RAM |
| bf16 | True | |
| max_length | **5120** | 实测覆盖 99% 样本 |
| dataloader_num_workers | **8** | 24 核 CPU 多进程喂数据 |
| `attn_implementation` | **flash_attention_2** | 长序列省 ~30% 显存、加速 1.5-2× |
| **assistant_only_loss** | **True** | 仅在 assistant 输出上算 loss |
| report_to | tensorboard + swanlab | 双开监控 |

---

## 8. 硬件资源与配置

### 服务器
| 资源 | 配置 |
|---|---|
| GPU | NVIDIA **A100 SXM4 80GB** ×1 |
| CPU | 24 核 |
| 内存 | 48 GB |
| SSD | 300 GB（已扩容） |
| OS | Ubuntu 22.04 LTS |
| CUDA 驱动 | 12.4 |

### 显存预算（max_seq=5120, bsz=2）
| 项 | 占用 |
|---|---:|
| 32B 模型权重（4bit nf4） | ~18 GB |
| LoRA 参数（r=16） | ~250 MB |
| 优化器状态（paged 8bit） | ~500 MB |
| 激活（grad ckpt + FA2） | ~28-36 GB |
| 临时 buffer / KV cache | ~2 GB |
| **总计** | **~50-60 GB** ✅ |

### CUDA 版本兼容性（已验证）
- Driver 12.4 ≥ torch wheel 内置 cu121 ≥ flash-attn wheel 内置 cu123
- 三层前向兼容，全部通过

---

## 9. 实验监控

### 双后端配置
1. **TensorBoard**：完全离线兜底，写到 `log/Fine_tuning/tensorboard/`
2. **SwanLab**（国产）：云端 dashboard，多 run 对比
   - workspace = `zhousy`
   - project = `ICKG-Baichuan-M2-32B-QLoRA`
   - experiment = `v1-5000samples-r16-lr1e-4`
   - API key 通过 `swanlab login` 一次性写入 `~/.netrc`，**不入仓库**

### 监控的指标
- 训练阶段：`train_loss`、`eval_loss`、`learning_rate`、`grad_norm`、训练步数
- 模型质量评估（业务指标）：JSON 合法率、实体/关系 ∈ 预定义集合的比例、与 ground-truth 的 P/R/F1 → **延后到推理阶段单独评估**

---

## 10. 服务器端操作流程（高度浓缩版）

```bash
# 1. 系统准备 + 磁盘扩容
apt-get install -y cloud-guest-utils
growpart /dev/vda 1 && resize2fs /dev/vda1

# 2. Miniconda + Python 3.10
bash Miniconda3-py310.sh -b -p /root/miniconda3
conda create -n ickg python=3.10 -y && conda activate ickg

# 3. 装依赖（pin trl>=0.16）
pip install torch==2.4.0 --index-url https://download.pytorch.org/whl/cu121
pip install transformers>=4.45 peft>=0.13 trl>=0.16 accelerate>=0.34 \
            datasets>=2.21 bitsandbytes>=0.43.3 swanlab>=0.4
pip install https://.../flash_attn-2.6.3+cu123torch2.4...-cp310-linux_x86_64.whl

# 4. 下载 base model
huggingface-cli download baichuan-inc/Baichuan-M2-32B \
    --local-dir /root/ICKG/models/hf/Baichuan-M2-32B

# 5. 烟测（20 步，~5 min）
python src/Fine_tuning/training/train_qlora.py \
    --config src/Fine_tuning/configs/train_config.yaml \
    --max-train-samples 50 --max-steps 20

# 6. 正式训练（3 epoch，~5-8 h）
tmux new -s train
python src/Fine_tuning/training/train_qlora.py \
    --config src/Fine_tuning/configs/train_config.yaml

# 7. 合并 LoRA → 完整权重
python src/Fine_tuning/training/merge_lora.py \
    --config src/Fine_tuning/configs/train_config.yaml --device auto
```

---

## 11. 关键代码片段

### 4bit 量化加载（PEFT 官方 QLoRA 标准）
```python
from transformers import AutoModelForCausalLM, BitsAndBytesConfig
from peft import prepare_model_for_kbit_training, LoraConfig

bnb_cfg = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_use_double_quant=True,
    bnb_4bit_compute_dtype=torch.bfloat16,
)
model = AutoModelForCausalLM.from_pretrained(
    "baichuan-inc/Baichuan-M2-32B",
    quantization_config=bnb_cfg,
    dtype=torch.bfloat16,                     # transformers 4.45+ 新 API
    device_map="auto",
    attn_implementation="flash_attention_2",
    trust_remote_code=True,
)
model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
```

### LoRA + SFTTrainer
```python
from peft import LoraConfig
from trl import SFTConfig, SFTTrainer

peft_config = LoraConfig(
    r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    task_type="CAUSAL_LM",
)
sft_cfg = SFTConfig(
    output_dir="...", num_train_epochs=3,
    per_device_train_batch_size=2, gradient_accumulation_steps=8,
    learning_rate=1e-4, lr_scheduler_type="cosine", warmup_ratio=0.03,
    optim="paged_adamw_8bit", bf16=True,
    max_length=5120,
    assistant_only_loss=True,                 # 只在 assistant 输出算 loss
    gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False},
    report_to=["tensorboard", "swanlab"],
)
trainer = SFTTrainer(
    model=model, args=sft_cfg,
    train_dataset=train_ds, eval_dataset=val_ds,
    peft_config=peft_config, processing_class=tokenizer,
)
trainer.train()
trainer.save_model("models/.../adapter")
```

### LoRA 合并
```python
from peft import PeftModel
base = AutoModelForCausalLM.from_pretrained(base_name, dtype=torch.bfloat16, device_map="auto")
peft_model = PeftModel.from_pretrained(base, "models/.../adapter")
merged = peft_model.merge_and_unload()
merged.save_pretrained("models/.../merged", safe_serialization=True)
```

---

## 12. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| 显存 OOM | 低 | 训练中断 | 降 `max_length 5120→4096`；降 `bsz 2→1`；关闭 FA2 |
| 模型下载失败 | 低 | 阻塞 | hf-mirror 镜像，断点续传；备用 modelscope |
| 6 种关系覆盖不足 50 篇 | 已知 | 模型对这几类抽取偏弱 | 数据本身限制，下一轮抓更多含这些关系的摘要补充 |
| 合并阶段磁盘 peak ~130 GB | 中 | 失败 | 300 GB SSD 已扩容，可容纳；OR 训练后只保留 adapter (~250 MB) |
| flash-attn 安装失败 | 中 | 速度降低 | yaml 中 `attn_implementation: null` 走 SDPA，不阻塞训练 |

---

## 13. 下一步（推理阶段，下一期沟通）

- 编写 `extract_triples.py`：加载 merged 权重，对剩余 68 万篇摘要做批量抽取（vLLM 加速）
- 编写评估脚本：JSON 合法率、实体/关系类型有效率、与 ground-truth 的 F1
- 与百川 M3 API 抽取结果做对比，决定是否再迭代一轮（更大 LoRA r / 更多训练数据）

---

## 14. 产出清单

```
prompts/
└── Triple_prompt_v2_finetune.md            精简版提示词（1,919 tokens）

src/Fine_tuning/
├── data_processing/
│   ├── 01_build_pmid_index.py              ┐
│   ├── 02_aggregate_by_pmid.py             │
│   ├── 03_stratified_sampling.py           │ 5 步数据流水线
│   ├── 04_build_sft_dataset.py             │
│   └── 05_split_train_val_test.py          ┘
├── training/
│   ├── train_qlora.py                      QLoRA 训练主脚本
│   ├── train_qlora.ipynb                   Notebook 版（同等功能）
│   ├── merge_lora.py                       LoRA 合并脚本
│   └── merge_lora.ipynb                    Notebook 版
└── configs/
    ├── data_config.yaml                    采样规则配置
    └── train_config.yaml                   训练超参配置

data/Fine_tuning_dataset/training_ready/v1/
├── train.jsonl  (4,500)                    ┐
├── val.jsonl    (250)                      │ 训练数据
├── test.jsonl   (250)                      │
├── sft_dataset.jsonl  (5,000)              │
├── sampled_5000_pmids.txt                  │
└── sampling_stats.json                     ┘

Plan/20260514/
├── Baichuan-M2-32B_QLoRA_Fine_tuning_Plan.md   主方案文档
├── Server_Operation_Manual.md              服务器手册（含凭证，gitignore）
└── PPT_Report.md                           本文档
```

---

## 15. 致谢与参考

- HuggingFace Course: Fine-tune Large Language Models（chapter 11）
- HuggingFace PEFT QLoRA 文档
- TRL SFTTrainer 文档（v0.25.0）
- QLoRA 原论文（Dettmers et al., 2023）
- Baichuan-M2-32B 模型权重（baichuan-inc）
- SwanLab 国产实验追踪平台

> 完
