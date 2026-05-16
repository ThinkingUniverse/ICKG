# Baichuan-M2-32B QLoRA 微调三元组抽取 — 实施方案

> 制定日期：2026-05-14  
> 范围：数据处理流水线 + QLoRA 训练（**不含推理脚本**，待训练验证后再单独沟通）

---

## 1. Context（为什么要做这件事）

已用百川 M3 API + 自写提示词，从 PubMed 免疫细胞领域 75 万篇摘要中抽取了两批共 72.4 万条三元组：
- **第一批**（v1 提示词，25 种关系）：~4 万篇 → 423,823 条三元组
- **第二批**（v2 提示词，89 种关系）：~3 万篇 → 300,931 条三元组（与第一批 PMID 无重叠）

两批数据都经过格式 / 实体 / 关系多阶段清洗。下一步目标：**用 QLoRA 微调 Baichuan-M2-32B**，使其按 v2 提示词标准抽取剩余 ~68 万篇摘要的三元组，从而把昂贵的 API 调用替换为可本地复用的开源模型推理。

---

## 2. 已定决策摘要

| 决策项 | 选择 | 理由 |
|---|---|---|
| 训练集规模 | **5,000 篇摘要** | QLoRA 在专业抽取任务上 3-8k 样本通常已收敛；单卡 A100 40GB 可在 1-2 天跑完 |
| 数据来源 | **仅用第二批** | 与 v2 提示词的关系空间完全对齐；第一批缺 induces / regulates / phosphorylates 等新增关系，混入会引入标签不一致 |
| 极低频关系 | **U / 反U → associated_with**，其余保留 | 60 / 36 例不足以学，合并到兜底关系；其他低频用过采保覆盖 |
| 关系再平衡 | **降采样 increases / 过采 associated_with** | 用户指出 v2 抽取中 increases 异常高于 associated_with，违反"associated_with 应为最常见兜底"的直觉，训练时通过分层调整修正 |
| score 过滤 | **不过滤** | 保留全部三元组，让模型学会输出 score；低分样本提供抽取边界感 |
| 微调提示词 | **新建精简版** | 实测 1,919 tokens（19 实体 + 87 关系表 + 输出格式）；训练 + 推理统一使用 |
| 框架 | **PEFT + BitsAndBytes（QLoRA）** | Baichuan-M2-32B 是新模型，Unsloth 是否优化支持未确认；PEFT 与任意 HF 模型兼容，更稳 |
| 分布式 | **不使用 DeepSpeed** | 单卡 40-48GB + 4-bit QLoRA 已足够，DeepSpeed 仅对多卡或全参微调必要 |
| GPU | **A100 SXM4 80GB ×1** ✅（已确认） | 32B + 4bit ≈ 18GB；LoRA + grad ckpt + max_seq=5120 + bsz=2 总计 ~50-60GB，80GB 有充足余量 |
| CPU / RAM / SSD | **24 核 / 48 GB RAM / 300 GB SSD** ✅（已扩容） | base ~65GB + merged ~65GB + checkpoints + 数据，约 140-160 GB |
| 实验监控 | **TensorBoard + SwanLab** 双开 | TB 完全离线兜底；SwanLab 用于多 run 对比与 dashboard |
| HF 镜像 | **hf-mirror.com** | 国内访问 HuggingFace 加速，写在 yaml `env:` 段，启动时自动设到 `os.environ` |
| 模型缓存路径 | `/root/ICKG/models/hf/` | 与项目同盘，避免家目录在其他卷导致双份 |

---

## 3. 文件与目录布局（新增，不动旧文件）

```
ICKG/
├── prompts/
│   └── Triple_prompt_v2_finetune.md       【新增】精简版提示词（实测 1,919 tokens）
│
├── src/Fine_tuning/                       【新增模块】
│   ├── data_processing/
│   │   ├── 01_build_pmid_index.py         构建 PMID → 摘要文本 索引
│   │   ├── 02_aggregate_by_pmid.py        三元组按 PMID 聚合 + U/反U 合并
│   │   ├── 03_stratified_sampling.py      分层采样 5000 PMID
│   │   ├── 04_build_sft_dataset.py        组装 messages → 训练样本 jsonl
│   │   └── 05_split_train_val_test.py     90 / 5 / 5 切分
│   ├── training/
│   │   ├── train_qlora.py                 PEFT QLoRA 训练主脚本
│   │   └── merge_lora.py                  训练完合并 LoRA → 完整权重（供后续推理阶段使用）
│   └── configs/
│       ├── data_config.yaml               采样比例、过滤阈值、随机种子等
│       └── train_config.yaml              所有训练超参（不写死在脚本）
│
├── data/Fine_tuning_dataset/training_ready/v1/   【新增】
│   ├── pmid_to_abstract.jsonl                    PMID → 摘要 索引
│   ├── pmid_to_triples.jsonl                     PMID → 三元组列表（合并 U/反U 后）
│   ├── sampled_5000_pmids.txt                    最终采样的 5000 个 PMID
│   ├── sampling_stats.json                       采样后实体/关系分布报告
│   ├── sft_dataset.jsonl                         全部 5000 条 messages 样本
│   ├── train.jsonl  (4500)
│   ├── val.jsonl    (250)
│   └── test.jsonl   (250)
│
├── models/Baichuan-M2-32B-QLoRA-v1/       【新增】
│   ├── adapter/                                  PEFT 保存的 LoRA 权重
│   ├── checkpoints/                              中间 checkpoint
│   └── merged/                                   合并后的完整 bfloat16 权重
│
└── log/Fine_tuning/                       【新增】训练日志与 TensorBoard
```

---

## 4. 数据处理流水线（5 步）

### Step 1 — 构建 PMID 索引（`01_build_pmid_index.py`）
- **输入**：`data/pubmed_output/merge/PubMed_abstract_2016_01_01_2026_03_31.json`（1.6GB）
- **输出**：`pmid_to_abstract.jsonl`，每行 `{"PMID": "...", "abstract": "...", "title": "..."}`
- 流式读取，避免一次性加载 1.6GB

### Step 2 — 按 PMID 聚合三元组（`02_aggregate_by_pmid.py`）
- **输入**：第二批 `triples_baichuan_m3_Add_ID_Format_Entity_Relation_Correct.jsonl`（300,931 行）
- **关系映射**：
  - `u_shaped_association_with` → `associated_with`
  - `inverted_u_shaped_association_with` → `associated_with`
  - 其他保留
- **输出**：`pmid_to_triples.jsonl`，每行 `{"PMID": "...", "n_triples": N, "triples": [...]}`，按 `score desc, ID2 asc` 排序

### Step 3 — 分层采样 5000 PMID（`03_stratified_sampling.py`）

采样规则（写在 `data_config.yaml`，可调）：
- **每篇三元组数分桶**（02 步已先把每篇截断到 30 条，所以无桶 D）：
  - 桶 A：3-7 条 — 40%（2000 篇）
  - 桶 B：8-15 条 — 40%（2000 篇）
  - 桶 C：≥16 条 — 20%（1000 篇）
  - 桶 0：<3 条 — 排除
- **关系类型覆盖保证**：每种关系**目标**至少出现在 50 篇训练样本中；从最稀缺关系开始，通过反向索引（关系→含它的 PMID 列表）强制纳入对应 PMID。
  - 实测结果：87 种关系中 81 种 ≥ 50 篇；6 种受数据本身限制（含它们的 PMID 在第二批中总数 < 50）覆盖 35-46 篇：`integrates 46 / excludes 44 / reaches 42 / selects 41 / complements 36 / competes_with 35`。这些关系**含它们的所有 PMID 几乎都被纳入了 5000 篇**。
- **降采样 increases**：含 increases 的 PMID 占比 ≤ 30%
- **过采 associated_with**：含 associated_with 的 PMID 占比 ≥ 35%
- **多样性**：同一 PMID 不重复

输出：`sampled_5000_pmids.txt`、`sampling_stats.json`（采样后分布报告）。实测达成：increases 30.00% / associated_with 51.44%。

### Step 4 — 组装 SFT 样本（`04_build_sft_dataset.py`）

每个样本为 OpenAI messages 格式（SFTTrainer 标准）：

```json
{
  "PMID": "12345678",
  "messages": [
    {"role": "system", "content": "<精简版 Triple_prompt_v2_finetune.md 的全部内容>"},
    {"role": "user",   "content": "<title + 空格 + abstract，再把连续空白压缩为单空格>"},
    {"role": "assistant", "content": "<JSON 数组，三元组列表>"}
  ]
}
```

`user` 内容拼接规则（与原始 API 调用 `scripts/Triple_extraction/Triple_extraction.py:278-282` 完全一致）：
```python
merged = f"{title.strip()} {abstract.strip()}".strip()
user_content = re.sub(r"\s+", " ", merged)
```

`assistant` 内容规则：
- JSON 数组，每元素含 `head / head_type / relation / tail / tail_type / source_sentence / score`
- **不保留 ID1 / ID2 / PMID**（节省 token）
- `ensure_ascii=False`、`separators=(",", ":")`（紧凑）

### Step 5 — 切分 train / val / test（`05_split_train_val_test.py`）
- 90 / 5 / 5 → 4500 / 250 / 250
- 按 PMID 切分；固定 `random_seed=42`

---

## 5. 精简版提示词（`Triple_prompt_v2_finetune.md`）

保留：
- 1 行角色描述
- 19 实体类型表（一行一种，去掉冗长 e.g.）
- 87 关系类型表（保留方向语义，一行一种）
- 输出格式说明（JSON 数组 + 字段含义）

去掉：
- 大段 Extraction Rules 解释
- 完整 Example（由 5000 个样本隐式学到）
- Boundary notes（同样隐式学）

**实测长度**：1,919 tokens（Qwen2.5 tokenizer）。原"目标 800 tokens"的预估严重低估了 87 个关系的累计长度，已据实修正。

---

## 6. 训练配置（`train_config.yaml`） — A100 80GB 优化版

```yaml
# 在 import HF 之前生效
env:
  HF_ENDPOINT: "https://hf-mirror.com"
  HF_HOME: "/root/ICKG/models/hf"

model:
  name_or_path: "baichuan-inc/Baichuan-M2-32B"   # 服务器上建议改为本地路径 /root/ICKG/models/hf/Baichuan-M2-32B
  trust_remote_code: true
  torch_dtype: "bfloat16"
  attn_implementation: "flash_attention_2"       # A100 + 长序列建议开 FA2；若装不上置为 null

quantization:
  load_in_4bit: true
  bnb_4bit_quant_type: "nf4"
  bnb_4bit_use_double_quant: true
  bnb_4bit_compute_dtype: "bfloat16"

lora:
  r: 16
  lora_alpha: 32
  lora_dropout: 0.05
  bias: "none"
  task_type: "CAUSAL_LM"
  target_modules: ["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"]

training:
  output_dir: "models/Baichuan-M2-32B-QLoRA-v1/checkpoints"
  num_train_epochs: 3
  per_device_train_batch_size: 2                 # 1→2，吞吐 ~2x
  per_device_eval_batch_size: 2
  gradient_accumulation_steps: 8                 # 16→8，保持有效 batch=16
  gradient_checkpointing: true
  learning_rate: 1.0e-4
  lr_scheduler_type: "cosine"
  warmup_ratio: 0.03
  optim: "paged_adamw_8bit"
  bf16: true
  max_grad_norm: 0.3
  weight_decay: 0.001
  logging_steps: 10
  save_steps: 200
  save_total_limit: 3
  eval_strategy: "steps"
  eval_steps: 200
  load_best_model_at_end: true
  metric_for_best_model: "eval_loss"
  report_to: ["tensorboard", "swanlab"]   # 双开
  dataloader_num_workers: 8                       # 24 核 CPU 多开数据加载

# SwanLab 项目设置（API key 不在此处，依赖 `swanlab login`）
swanlab:
  enabled: true
  project: "ICKG-Baichuan-M2-32B-QLoRA"
  workspace: "zhousy"                     # SwanLab 个人/组织 workspace
  experiment_name: "v1-5000samples-r16-lr1e-4"
  description: "Baichuan-M2-32B 4bit QLoRA on 5000 PubMed immunology abstracts, second batch"
  mode: "cloud"

sft:
  max_seq_length: 5120                 # A100 80GB 有余量，覆盖 99% 样本不截断（实测 max=5648）
  packing: false
  data_path: "data/Fine_tuning_dataset/training_ready/v1"

seed: 42
```

---

## 7. 显存预算（A100 80GB）

| 项 | 估算 |
|---|---|
| 32B 模型权重（4bit nf4） | ~18 GB |
| LoRA 参数（r=16，all-linear） | ~250 MB |
| 优化器状态（paged_adamw_8bit） | ~500 MB |
| 激活（max_seq=5120, **bsz=2**, grad ckpt 开，FA2 开） | ~28-36 GB |
| 临时 buffer / KV cache | ~2 GB |
| **总计** | **~50-60 GB**（A100 80GB 有 20+ GB 余量） |

进一步优化空间（如果想更快）：
- 关 `gradient_checkpointing` → 速度 1.5-2x，但显存 +20-30 GB，可能爆
- 提 `lora.r` 到 32 / 64 → 更多可学参数，对长尾关系学习更稳
- 这两项建议第 2 次迭代时尝试

OOM 应急方案（按优先级）：
1. `max_seq_length` 5120 → 4096
2. `per_device_train_batch_size` 2 → 1（`gradient_accumulation_steps` 8 → 16 保持有效 batch）
3. 关 `attn_implementation` 改为 null
4. LoRA `r` 16 → 8

---

## 8. 验证步骤

1. 环境：`conda activate lckg`，本地数据处理需 `PyYAML / ijson`；服务器训练需 `peft / trl / bitsandbytes / accelerate / transformers>=4.45 / datasets / PyYAML / swanlab`
   - 在服务器一次性执行：`pip install swanlab && swanlab login`（API key 输入一次即可，存到 `~/.netrc`；**不要把 key 写进任何配置文件或脚本**）
   - 设置 HF 缓存目录到 SSD：`export HF_HOME=/your_ssd_path/hf_cache`，避免家目录在另一块盘上时模型双份占用
2. **本地已完成 ✅**：依次跑 01 → 05，已经核对 `sampling_stats.json` 中关系分布符合再平衡目标（increases 30.00% / associated_with 51.44%）
3. **本地已完成 ✅**：用 Qwen2.5 tokenizer 实测，total p95 ≈ 3949 tokens，`max_seq_length=4096` 覆盖 95% 样本
4. 服务器小规模训练验证：`python train_qlora.py -c ... --max-train-samples 50 --max-eval-samples 20 --max-steps 20`。`max_steps=20` 含义：训练只跑 20 个 optimizer step（一个 step = bsz×grad_accum = 16 个样本，所以 20 步 ≈ 320 样本），用于快速确认管道无 OOM、loss 下降
5. 完整训练：3 epoch，监控 train/eval loss
6. 合并权重：`merge_lora.py` → 保存到 `models/.../merged/`（推理与评估代码本期不写，训练完成后再讨论）

---

## 9. 不在本期范围内的（明确剔除）

- 推理脚本（待训练完成后单独沟通）
- DeepSpeed / 多卡 / FSDP
- Unsloth（除非后续验证 Baichuan-M2-32B 被官方支持）
- 全参微调
- 强化学习 / DPO 对齐阶段

---

## 10. 配套文档

- 服务器端从登录到训练结束的完整操作步骤：见同目录 `Server_Operation_Manual.md`（**含登录凭证，已 gitignore，不会推送到远端**）。
