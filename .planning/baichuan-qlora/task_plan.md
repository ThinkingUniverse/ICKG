# Task Plan — Baichuan-M2-32B QLoRA 三元组抽取微调

> Plan ID: baichuan-qlora ・ 创建 2026-06-01 ・ 语言中文
> 实施方案：[Fine_tuning_Plan](../../Plan/fine-tuning/Baichuan-M2-32B_QLoRA_Fine_tuning_Plan.md)
> 服务器手册：[Server_Operation_Manual](../../Plan/fine-tuning/Server_Operation_Manual.md)
> 报错复盘：[error/smoke-test 评估报告](../../error/smoke-test/烟测报错处理评估报告.md)

## 当前阶段
**Phase 6 — 正式训练前 checklist + 启动 3 epoch 训练**（服务器 /root/ICKG，tmux 内）。
下一步：先完成下方 🔴 必做项，再开训。

## 阶段总览
| # | 阶段 | 状态 |
|---|---|---|
| 1 | 数据处理流水线 01–05（本地） | ✅ complete |
| 2 | 精简版提示词 Triple_prompt_v2_finetune.md（1,919 tok） | ✅ complete |
| 3 | 训练数据 v1 切分 train4500/val250/test250 | ✅ complete |
| 4 | 服务器环境搭建（env ickg，版本已锁） | ✅ complete |
| 5 | 烟测 20 步（显存 64.6G/79%，3 报错已修） | ✅ complete |
| 6 | 正式训练 3 epoch（~14.3h，¥100） | 🔄 in_progress（待启动） |
| 7 | 合并 LoRA → merged bf16 | ⏸️ pending |
| 8 | test.jsonl 评估 + adapter 推理 prompt 对齐校验 | ⏸️ pending |
| 9 | 下载结果到本地 + 清理服务器 | ⏸️ pending |
| 10 | vLLM 推理 680k 摘要（本期范围外） | 🔮 future |

---

## Phase 6 待办（开训前 checklist，摘自评估报告 §4）
- [ ] 🔴 确认 requirements-server-finetuning.txt 已锁版本（torch2.6.0/transformers5.8.1/peft0.19.1/accelerate1.13.0/bnb0.49.2/trl1.4.0）
- [ ] 🟡 warmup_ratio→warmup_steps、logging_dir→环境变量（当前仍可用，可选）
- [ ] 🟡 train_qlora.py 加 tokenizer reload sanity check（评估报告 §3.7.1）
- [ ] 🟡（可选）先跑 500 样本中尺度烟测，复核 step time/显存
- [ ] 清理烟测残留 adapter/ 与 checkpoints/（手册 §11.0）
- [ ] tmux 内启动 3 epoch 训练（手册 §11.2），SwanLab+TensorBoard 监控（§12）

## Phase 7–9 关键提醒
- merge：`merge_lora.py --test-after-merge 5`（手册 §13）
- 🔴 vLLM 铁律：**不要传 thinking_mode**（评估报告 §3.6）；部署前跑 prompt 尾部 assert
- 磁盘：vda1 128G 顶在上沿，merged 65G 前盯 `df -h /`（手册 §3.5）

## Errors Encountered
烟测 3 类报错均已修复（详见 findings.md 与 error/smoke-test/）。遗留 🟡：第三处模板「字节完全一致」表述待订正。
