# Task Plan — Baichuan-M2-32B QLoRA 三元组抽取微调

> Plan ID: baichuan-qlora ・ 创建 2026-06-01 ・ 语言中文
> 实施方案：[Fine_tuning_Plan](../../Plan/fine-tuning/Baichuan-M2-32B_QLoRA_Fine_tuning_Plan.md)（§12 = 推理执行结果）
> 服务器手册：[Server_Operation_Manual](../../Plan/fine-tuning/Server_Operation_Manual.md)（§18 = vLLM 推理运维）
> 报错复盘：[error/smoke-test 评估报告](../../error/smoke-test/烟测报错处理评估报告.md)

## 当前阶段
**Phase 10（vLLM 推理 684k）已完成收官**（2026-06-26）。
全流程：数据处理 → QLoRA 训练 → 合并 → vLLM 推理 68 万篇 → 截断补尾停止+合并定稿 → 数据回传本地 + 公开发布到 HuggingFace。
最终产物 `data/vllm_inference/output/triples_merged.jsonl`：**684,149 篇 / 7,863,996 条三元组（786 万，2.6GB）**。下游 = 实体对齐（`scripts/Entity_alignment`）。

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
| 8 | test.jsonl 完整评估 + adapter 推理 prompt 对齐校验 | 🟡 部分（对齐校验✅ + 抽检✅，完整评估未做） |
| 9 | 数据回传本地 + 公开发布 HF（数据集 + adapter） | ✅ complete |
| 10 | vLLM 推理 684,153 篇摘要 + 截断补尾停止定稿 | ✅ complete（684,149篇 / 786万三元组 / triples_merged.jsonl） |

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

## 关键铁律（贯穿推理）
- 🔴 vLLM 不传 thinking_mode（评估报告 §3.6），prompt 末尾须 `<|im_start|>assistant\n`（verify_adapter_inference_alignment.py 已校验）。
- 🔴 serve 用 base 词表（merged 缺 vocab.json/merges.txt）。

---

## Phase 10 — vLLM 推理（2026-06-03 规划 → 2026-06-26 收官）

### 数据盘点（本地流式实测，ijson）
- 全量 752,078 篇 − 已提取 67,925（两批 triples_usage.jsonl，零交集）= **剩余 684,153 篇**。
- 输入 = Title+Abstract 合并；输出 schema 每行一条三元组（8 字段）。

### 最终落地（实测，与原规划/预估的差异以此为准）
- **部署**：Online Serving（vllm serve + 异步客户端）。**环境**：独立 `vllm_env`（vllm0.8.5.post1 + torch2.6cu124 + transformers4.51.3；驱动 550/CUDA12.4 锁版本）。
- **生成参数（质量优先）**：bf16 / temperature 0 / max_tokens 2560 / 并发 32。拒绝 fp8 KV（实测能提速 2.3x 但有量化误差）与 int4 量化。
- 🔴 **复读坑 + 根治**：贪心+高并发批次非确定性 → 约 10–24% 文章复读刷到 max_tokens（丢数据+霸占 KV）。客户端加 `salvage_objects`（残片打捞）+ 5元组去重（failed 89→0、截断篇全救回）；max_tokens 4096→2560（吞吐 0.40→0.49）。
- 🔴 **客户端会静默卡死**：曾卡死 3.5 天空转浪费 ~580 元 → 新增监工 `run_extract_supervised.sh`（STALL 检测自愈重启）。
- **截断补尾停止**：69,068 截断篇，6144 上限下仅 0.04 篇/s、净增 +0.3 条/篇，外推 ~20 天/~3,362 元 ROI 极差 → 用户决定停止（已补 511 篇并入），`06 --merge-only` 定稿。
- **实测吞吐 ~0.49 篇/s**（GPU 98% 满载），全量 ~16 天净跑；费用量级数千元（远超原 §11 预估的 ¥170）。
- **不需重训**：训练集答案 token 中位 633 / p99 2152 / max 3631，被 5120 截断仅 0.22%。

### 产物与发布
- 最终：`data/vllm_inference/output/triples_merged.jsonl`（786 万三元组）；已压缩回传本地。
- HF 公开：[数据集](https://huggingface.co/datasets/Siyu2Zhou/ICKG-immunology-triple-extraction-sft) + [adapter](https://huggingface.co/Siyu2Zhou/Baichuan-M2-32B-QLoRA-immunology-triples)（含完整 tokenizer/chat_template/复现 README）。

### 脚本清单（scripts/vllm_inference/）
01_filter_split.py（本地分片）/ 02_serve_vllm.sh / 03_extract_client.py（打捞去重）/ 05_check_answer_token_len.py / 06_recover_truncated.py（补尾合并）/ run_extract_supervised.sh（监工）/ run_recover_after_main.sh（编排）。

---

## Errors Encountered（累计）
- 烟测 3 类报错（torch/SwanLab/trl 模板）已修，详见 findings.md 与 error/smoke-test/。
- 合并 OOM（merge_exit=137）：加 swap 已解。
- Phase 10：vllm cu13 不兼容（锁 0.8.5.post1）/ merged 慢速 tokenizer 崩（serve 用 base 词表）/ 贪心复读丢数据（打捞去重）/ 客户端静默卡死（监工）/ 国内→HF 大文件超时（hf_transfer）。详见 findings.md「Phase 10 推理踩坑与定论」「Phase 10 收官」。

## 后续（下一阶段）
- Phase 8 完整 test.jsonl 业务评估（可选，未做）。
- 实体对齐与链接：用 triples_merged.jsonl 构建 KG（`scripts/Entity_alignment`）。
- 服务器：控制台停机止损（停机保留磁盘）；输出数据已回传本地。
