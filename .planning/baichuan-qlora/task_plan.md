# Task Plan — Baichuan-M2-32B QLoRA 三元组抽取微调

> Plan ID: baichuan-qlora ・ 创建 2026-06-01 ・ 语言中文
> 实施方案：[Fine_tuning_Plan](../../Plan/fine-tuning/Baichuan-M2-32B_QLoRA_Fine_tuning_Plan.md)
> 服务器手册：[Server_Operation_Manual](../../Plan/fine-tuning/Server_Operation_Manual.md)
> 报错复盘：[error/smoke-test 评估报告](../../error/smoke-test/烟测报错处理评估报告.md)

## 当前阶段
**Phase 7 已完成；Phase 10（vLLM 推理 684k）启动规划**（2026-06-03）。
merged bf16 已生成（62G）并通过 test.jsonl 抽检 + test-paper-2 两篇文章人工抽检（JSON 全合法）。
Phase 8/9 仍可选。本轮重点：用 merged 模型 vLLM 推理抽取**剩余 684,153 篇**摘要的三元组。
→ 详见下方「Phase 10」小节；部署方式/本轮范围/压测方式待用户确认后执行。

## 阶段总览
| # | 阶段 | 状态 |
|---|---|---|
| 1 | 数据处理流水线 01–05（本地） | ✅ complete |
| 2 | 精简版提示词 Triple_prompt_v2_finetune.md（1,919 tok） | ✅ complete |
| 3 | 训练数据 v1 切分 train4500/val250/test250 | ✅ complete |
| 4 | 服务器环境搭建（env ickg，版本已锁） | ✅ complete |
| 5 | 烟测 20 步（显存 64.6G/79%，3 报错已修） | ✅ complete |
| 6 | 正式训练 3 epoch（实测18.8h/¥131，train_loss0.067，eval_loss0.0745） | ✅ complete |
| 7 | 合并 LoRA → merged bf16（62G，OOM→加swap修复） | ✅ complete |
| 8 | test.jsonl 完整评估 + adapter 推理 prompt 对齐校验 | 🟡 部分（对齐校验✅ + 抽检✅，完整评估待做） |
| 9 | 下载结果到本地 + 清理服务器（含 swap） | ⏸️ pending |
| 10 | vLLM 推理 684,153 篇摘要 | 🟢 运行中（远程 bf16 全量，~0.42篇/s≈19天，0截断） |

---

## Phase 6 训练结果（2026-06-03 02:19:49 完成，python_exit=0）
- 846/846 步，train_runtime≈67760s（18.8h，稳态~76–80s/it），train_loss 0.06715
- eval_loss：step200=0.0784 / 400=0.0748 / 600=0.0746 / 800=0.0745 / epoch3末=0.07451（最优），token准确率~97.56%，无过拟合
- 产物：models/Baichuan-M2-32B-QLoRA-v1/adapter/（adapter_model.safetensors 537MB + tokenizer + 官方模板，已校验与base字节一致）

## Phase 7 合并结果（2026-06-03 03:34）
- 磁盘：vda 扩到 228G，growpart /dev/vda 1 + resize2fs → vda1=225G、可用~132G
- 合并首次 OOM（merge_exit=137）：RAM 仅 47G 无 swap，save 时 bf16 32B gather 到 CPU 爆内存；建 32G swapfile 修复后成功
- merged=62G（model-0000{1,2}-of-00002.safetensors + tokenizer + chat_template）；--test-after-merge 2 通过
- 新增 src/Fine_tuning/tools/extract_triples_infer.py（文章→title+abstract合并→精简版system→merged生成，不传thinking_mode）
- test-paper-2 抽检：PMID39893935(sepsis)13条 / PMID41767601(睡眠饮食免疫)8条，均JSON合法 → models/Baichuan-M2-32B-QLoRA-v1/inference_test/test-paper-2_pred.{json,md}

## Phase 8–9 关键提醒
- 🔴 swap 临时（未写 /etc/fstab，重启失效）；再次合并/大内存任务前需重建：dd 32G→mkswap→swapon
- 🔴 vLLM 铁律：不要传 thinking_mode（评估报告 §3.6）；部署前跑 prompt 尾部 assert（已用 verify_adapter_inference_alignment.py 校验通过）
- 下载前 df -h /；清理：swapoff /swapfile && rm /swapfile 可回收 32G
- 基座 models/hf/Baichuan-M2-32B(63G) 合并已用完，如需空间可删回收

## Errors Encountered
- 烟测 3 类报错已修复（详见 findings.md 与 error/smoke-test/）
- 合并 OOM（merge_exit=137）：加 swap 已解；推理脚本 apply_chat_template 返回 BatchEncoding 需 return_dict=True，已修

---

## Phase 10 — vLLM 推理抽取剩余 684,153 篇摘要（2026-06-03 启动规划）

### 数据盘点（本地流式实测，ijson）
- 全量 `data/pubmed_output/merge/PubMed_abstract_2016_01_01_2026_03_31.json` = **752,078** 篇（对象数组；PMID 无重复、摘要无为空；1.65GB）
- 已提取（按两批 `triples_usage.jsonl` 的 PMID）：First=40,256 + Second=27,987，两批零交集 → **67,925** 篇
- 剔除后剩余 = **684,153** 篇（≈68 万，与预期吻合）
- 每篇字段：PMID / Title / Abstract（+DOI/Journal 等）
- 下游三元组输出 schema（已固定，须对齐）：每行一条三元组 = `{PMID, head, head_type, relation, tail, tail_type, source_sentence, score}`

### 提示词 / 生成参数（与训练对齐 = 铁律）
- system = `prompts/Triple_prompt_v2_finetune.md`（精简版 1,919 tok）
- user = `merge_title_abstract`：`title.strip()+空格+abstract.strip()`，`re.sub(r"\s+"," ")`（与 04_build_sft_dataset.py 一致）
- chat template：`add_generation_prompt=True`，🔴**不传 thinking_mode**（否则注入未训练的 `<think>`，破坏分布）
- `temperature=0.1`、`max_new_tokens≈2560`（覆盖训练 assistant max≈2326）
- token 分布（来自已提取 usage）：prompt≈3.4k–4.6k，completion≈2.1k–4.9k → **max_model_len 设 8192 安全**

### 步骤
1. (本地) `filter_split` 脚本：流式 ijson 读全量 → 剔除 done PMID 集合 → 输出推理输入分片 JSONL（`{PMID, user_content}`），分片数可配置（默认 ~20 片）。
2. (远程) 建 `vllm_env`（python3.12 + vllm），`vllm serve merged`（OpenAI 兼容）；`--gpu-memory-utilization≈0.95`、`--max-model-len 8192`、`--served-model-name baichuan-m2-qlora`，挂 nohup/tmux。
3. (远程) 异步 OpenAI 客户端：高并发推流 684k、增量写 JSONL、done-pmid 断点续跑、失败/截断单独记账、把模型输出的 JSON 数组 explode 成单条三元组（对齐既有 schema）。
4. (远程) 压测：先用真实数据 1k–5k 小样本跑客户端测端到端吞吐（最准）；可选 evalscope perf 扫 `--parallel` 找并发甜点。据吞吐外推总耗时×单价 → 决定充值额度。
5. (远程) 正式跑全量 → 产物下载回本地，并入 KG 构建（Entity_alignment 下游）。

### 关键抉择（待用户确认）
- **部署方式**：推荐 **Online Serving**（vllm serve + 异步客户端）——压测需 HTTP 端点；解耦 + 断点续跑对多小时长任务更稳；吞吐与 Offline 等价（同引擎连续批处理）。Offline `LLM.generate` 备选：单脚本最简，但崩溃即全失，且 evalscope 压测仍需另起服务。
- **本轮范围**：本地数据准备可立即做；vLLM/压测脚本可本地编写（仓库镜像到远程），实际执行需切到远程（用 remote-server-ops）。
- **压测方式**：推荐真实数据小样本 pilot（最准）；evalscope 合成压测可选作并发调参。

### 硬件 / 吞吐预估（单 A100 80GB，TP=1）
- 32B bf16 权重 ≈62–64G，`gpu_mem_util 0.95` → KV cache 仅 ~12G，并发受限；可试 `--kv-cache-dtype fp8` 翻倍 KV，或靠 `max_model_len 8192` 控住每序列 KV。
- A100=Ampere，无原生 FP8 权重加速；若需更高吞吐再评估 AWQ/GPTQ int4（需另量化、可能损质量，压测后定）。
- GPU 计算是瓶颈，目标 = 喂满并发吃满 GPU（CPU/RAM 不必跑满）；min wall-clock = GPU 饱和。
