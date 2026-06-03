# Task Plan — Baichuan-M2-32B QLoRA 三元组抽取微调

> Plan ID: baichuan-qlora ・ 创建 2026-06-01 ・ 语言中文
> 实施方案：[Fine_tuning_Plan](../../Plan/fine-tuning/Baichuan-M2-32B_QLoRA_Fine_tuning_Plan.md)
> 服务器手册：[Server_Operation_Manual](../../Plan/fine-tuning/Server_Operation_Manual.md)
> 报错复盘：[error/smoke-test 评估报告](../../error/smoke-test/烟测报错处理评估报告.md)

## 当前阶段
**Phase 7 已完成 → 入口 Phase 8/9**（服务器 /root/ICKG）。
merged bf16 已生成（62G）并通过 test.jsonl 抽检 + test-paper-2 两篇文章人工抽检（JSON 全合法）。
下一步可选：Phase 8 完整 test.jsonl 评估；Phase 9 下载结果到本地 + 清理服务器（含临时 swap）。

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
| 10 | vLLM 推理 680k 摘要（本期范围外） | 🔮 future |

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
