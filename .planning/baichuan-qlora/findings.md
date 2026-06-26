# Findings — Baichuan-M2-32B QLoRA

> 决策与知识沉淀。完整方案见 [Fine_tuning_Plan](../../Plan/fine-tuning/Baichuan-M2-32B_QLoRA_Fine_tuning_Plan.md)（§12 推理）；运维见 [Server_Operation_Manual](../../Plan/fine-tuning/Server_Operation_Manual.md)（§18）。

## 关键决策（速查）
- 训练集 5000 篇，仅用第二批（与 v2 提示词 89 关系对齐）；U/反U → associated_with
- 再平衡达成：increases 30.00% / associated_with 51.44%
- QLoRA（PEFT + bnb 4bit nf4），r=16 / alpha=32，7 层 linear；不用 DeepSpeed/Unsloth
- A100 80GB×1；max_seq=5120；bsz2 × grad_accum8 = 16；3 epoch = 843 步 × 61s ≈ 14.3h
- 监控 TensorBoard + SwanLab；HF 走 hf-mirror；提示词精简版实测 1,919 tok

## 烟测实测（2026-05-18）
- 显存峰值 64.6/80GB（79%），GPU 99%，423W；每 step 61s
- loss 0.124 / eval 0.124 / token_acc 0.96（管道通；数据太小无参考意义）

## 报错知识库（[error/smoke-test/](../../error/smoke-test/)）
1. torch infer_schema 字符串注解 → 升 torch 2.6.0+cu124（🟢 已修，干净）
2. SwanLab max_seq_length KeyError → 兼容回退（🟢 已修）
3. trl assistant_only_loss 模板 → 训练专用简化模板 baichuan_m2_training_template.jinja（⚠️ 已修，有对齐约束）
   - ⚠️ 训练-推理对齐依赖隐式约定：推理/vLLM **不传 thinking_mode**，否则喂入训练没见过的 `<think>` 前缀
   - 详见 [评估报告 §3](../../error/smoke-test/烟测报错处理评估报告.md)；「字节完全一致」表述需订正

## 范围外（训练期不做）
DeepSpeed/多卡/FSDP、全参微调、RL/DPO（仍不做）

## 正式训练实测（2026-06-03）
- **稳态步时 ~76–80 s/it，比手册烟测估算的 61 s/step 慢约 30%**：18.8h/¥131 vs 手册 14.3h/¥100。原因：61s 取自前 20 步烟测、早于最终配置定稿。→ 后续估时用 ~78 s/it。
- **eval_loss 单调小幅降到 0.0745 平台、eval≈train**：3 epoch 充分，无明显过拟合。
- 磁盘是 Phase 7 硬约束：merged bf16 ≈65G 额外新增，须先扩容根盘到可用 ~100G。

## Phase 10 推理踩坑与定论（2026-06-04）
- 环境：驱动 550/CUDA12.4 → 锁 vllm0.8.5.post1 + torch2.6.0cu124 + transformers4.51.3；serve 用 base 词表 models/hf/Baichuan-M2-32B（merged 缺 vocab.json/merges.txt 致 slow tokenizer 崩）；pip 改阿里云镜像。
- 复读根因：贪心 temperature0 在 vLLM 高并发下「批次数值不确定性」→ 约 10-24% 文章复读同一三元组刷到 max_tokens（既丢数据又霸占 KV 槽位拖垮吞吐）；隔离单测同篇时好时坏可证。rep_penalty 能断但误伤召回（结构 token 被罚 13→7），小温度也压不住。
- 定论修复：客户端「残片打捞 salvage_objects + 按 head/head_type/relation/tail/tail_type 去重」（failed 89→0、截断篇 23/23 全救回）；max_tokens 4096→2560（截短复读浪费、覆盖训练 p99=2152、吞吐 0.40→0.49）；temperature 保持 0。
- 训练集答案 token 分布核验（05 脚本）：中位 633 / p99 2152 / max 3631，full>5120 仅 0.22% → 训练目标几乎没被截断，不需重训。
- 截断篇定性：唯一三元组中位 14（高于正常篇 10），主要是真·内容丰富而非复读，0 篇彻底丢失；少数超长篇丢尾（如 19→38）。

## Phase 10 收官（2026-06-26）
- **吞吐铁律**：bf16 单 A100 跑 32B，**~0.49 篇/s**（GPU 98% 满载，KV cache 仅 ~48k token、典型并发 ~10–16）。68 万篇是"天/周"级任务，**估时务必用 0.49 篇/s**，原手册 §11「6–10 req/s / ¥170」严重低估。
- **客户端静默卡死（重大教训）**：writer 协程异常死锁→队列塞满→worker 全卡、进程不退也不报错。曾**卡死 3.5 天、GPU 空转浪费 ~580 元**才发现。→ 必须监工 `run_extract_supervised.sh`（STALL 检测自愈）。服务端正常，重启客户端即恢复。
- **fp8 KV 提速但不用**：实测 `--kv-cache-dtype fp8` 把 12288 并发上限 3.98x→8.82x（~2.3 倍），但量化有误差，按质量优先放弃。
- **补尾 ROI 极差 → 停止**：69,068 截断篇，6144/temp0.5 下仅 0.04 篇/s、净增 +0.3 条/篇，外推 ~20 天/~3,362 元。截断篇经残片打捞已有中位 14 条（高于正常），决定停补尾、`06 --merge-only` 定稿（仅并入已补 511 篇）。**结论：salvage 之后截断不再等于丢数据，一般无需补尾。**
- **最终产物**：`data/vllm_inference/output/triples_merged.jsonl` = 684,149 篇 / 7,863,996 条三元组（786 万，2.6GB），已压缩回传本地。
- **发布**：HF 公开数据集 + adapter（含完整 tokenizer/chat_template/复现 README）；国内→HF 大文件用 hf_transfer + 重试循环解决超时。
- **本地钩子**：`.claude/hooks/enforce_ickg_env.py` 拦含 `python` 的本地命令；远端跑 python 要改写 .sh 再 bash，或用 cat/scp/hf/curl/wc。

## 下游
triples_merged.jsonl（786 万三元组）→ 实体对齐与链接（scripts/Entity_alignment）构建 KG。
