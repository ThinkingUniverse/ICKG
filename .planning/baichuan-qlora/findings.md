# Findings — Baichuan-M2-32B QLoRA

> 决策与知识沉淀。完整方案见 [Fine_tuning_Plan](../../Plan/fine-tuning/Baichuan-M2-32B_QLoRA_Fine_tuning_Plan.md)。

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

## 范围外（本期不做）
推理脚本（训练后单聊）、DeepSpeed/多卡/FSDP、全参微调、RL/DPO

## 正式训练实测（2026-06-03）
- **稳态步时 ~76–80 s/it，比手册烟测估算的 61 s/step 慢约 30%**：18.8h/¥131 vs 手册 14.3h/¥100。原因推断：61s 取自前 20 步烟测、且早于最终 bsz2+grad_accum8+max_length5120 配置定稿，满序列 fwd+bwd 更重。→ 后续估时直接用 ~78 s/it。
- **eval 单次 ~6.2 min（374s，250 样本/eval_bsz2/125 batch）**，eval_steps=200 全程 4 次 + epoch 末 1 次，开销总计 ~25–30 min，量级可控。
- **eval_loss 单调小幅下降到 0.0745 平台、eval≈train**：r16/lr1e-4/3epoch 对该任务无明显过拟合，3 epoch 充分；若赶时间 2 epoch 也基本到位。
- **SwanLab cloud 训练全程间歇 network error 但自动续传**，本地 TensorBoard + swanlog 离线缓存兜底，不影响权重与最终结果。
- **磁盘是 Phase 7 硬约束**：merged bf16 ≈65G 为额外新增，基座 63G 为合并输入不可删；128G 根盘（训练后可用仅 38G）放不下，须先扩容到可用 ~100G。
