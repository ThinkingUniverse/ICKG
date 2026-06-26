# Progress Log — Baichuan-M2-32B QLoRA

> 追加式日志，最新在底部；每完成一步追加一条。

- 2026-05-14 制定实施方案（Fine_tuning_Plan）
- 2026-05-14~18 本地数据处理 01–05 完成，sampling_stats 达标（increases 30.00% / associated_with 51.44%）；提示词精简版 1,919 tok；train/val/test 切分完成
- 2026-05-15 服务器操作手册初稿
- 2026-05-18 烟测 20 步通过（显存 64.6G，loss 0.124）；踩坑 3 类报错并修复（torch / SwanLab / trl 模板）
- 2026-05-28 服务器增补：vda1 扩到 128G；env ickg 版本锁定；评估报告完成，给出开训前 checklist
- 2026-06-01 用 planning-with-files 建立 .planning/baichuan-qlora/ 状态层（三件套），链接现有文档
- （下一条）待：完成开训前 checklist → tmux 启动 3 epoch 训练
- 2026-06-02 07:27 tmux 会话 `train` 内启动正式 3 epoch 训练（launcher: log/Fine_tuning/run_train.sh，日志 log/Fine_tuning/train_20260602_072736.log）。开训前 checklist 全过：模型63G / 数据4500·250·250 / flash-attn2.6.3 / SwanLab已登录cloud / 磁盘40G可用 / 无烟测残留。已确认进入训练循环：总步数 846，GPU 78.8G·100%，首步 81s/it（含预热，稳态预计回落）。下一步：监控 SwanLab loss 曲线，训练结束后进入 Phase 7 合并 LoRA。
- 2026-06-03 02:19:49 ✅ 正式 3 epoch 训练完成（python_exit=0）。846/846 步跑满，train_runtime≈67760s（18.8h，实测稳态~76–80s/it，比手册61s估算慢约30%），实际费用≈¥131。train_loss 0.06715。
  - eval_loss 逐步下降并平台：step200=0.07842 / 400=0.07477 / 600=0.07460 / 800=0.07454 / epoch3末=0.07451（最优），token准确率~97.56%，eval≈train 无过拟合；load_best_model_at_end 已生效。
  - 产物：models/Baichuan-M2-32B-QLoRA-v1/adapter/（adapter_model.safetensors 537MB + tokenizer + chat_template.jinja，官方模板已还原并校验与base字节一致）；checkpoints/ 保留 400/600/800（各529MB）。
  - tmux 会话 train 已随 launcher 结束自动退出，GPU 已释放（1MiB）。SwanLab 训练中有间歇 network error 但已自动续传，run: https://swanlab.cn/@zhousy/ICKG-Baichuan-M2-32B-QLoRA
  - ⚠️ Phase 7 合并阻塞于磁盘：merged(bf16)≈65G 为额外新增，当前根盘 vda1 仅 38G 可用（缺~27G）。已请管理员在线扩容 vda1 ~190–200G（再加~65G，可用达~100G）。用户将关机以便加盘。重启后从 Phase 7 续：merge_lora.py --test-after-merge 5（合并前先 df -h /）。
- 2026-06-03 03:34 ✅ Phase 7 合并完成 + test-paper-2 推理测试。
  - 磁盘：管理员把 vda 扩到 228G；growpart /dev/vda 1 + resize2fs 后 vda1=225G、可用~132G，无需新建分区。
  - 合并首次失败 merge_exit=137（OOM）：根因服务器 RAM 仅 47G 且无 swap，save_pretrained 把 bf16 32B(~64G) gather 到 CPU 内存爆掉（dmesg 实证 anon-rss 47.5G 被 oom-killer 杀）。修复：建 32G swapfile(/swapfile)兜住峰值后重跑成功。merged=62G（model-0000{1,2}-of-00002.safetensors + tokenizer + chat_template）。--test-after-merge 2 通过（13/5 三元组、JSON 合法、与 GT 吻合）。
  - 新增推理脚本 src/Fine_tuning/tools/extract_triples_infer.py：读文章 JSON → title+abstract 按训练一致方式合并(re.sub 压空白) → 精简版 system 提示词 → merged 生成（不传 thinking_mode）→ 输出结构化 JSON + 人工查看 MD。踩坑：apply_chat_template(tokenize=True,return_tensors=pt) 返回 BatchEncoding 非 tensor，须 return_dict=True 且 generate(**inputs)。
  - test-paper-2.json(2 篇)结果：PMID 39893935(sepsis/肠道菌群,EBioMedicine) 13 条；PMID 41767601(睡眠饮食/免疫,Research) 8 条；均 JSON 合法，关系/类型走预定义体系，source_sentence 可溯源。输出 → models/Baichuan-M2-32B-QLoRA-v1/inference_test/test-paper-2_pred.{json,md}。
  - ⚠️ swap 临时（未写 /etc/fstab，重启失效）；merged 推理靠 low_cpu_mem 分片加载、无 swap 也能跑，但若再次合并需重建 swap。下一步可选 Phase 8 完整 test.jsonl 评估、Phase 9 下载+清理。
- 2026-06-03 启动 Phase 10（vLLM 推理 684k）规划。本地流式盘点：全量 752,078 − 已提取 67,925 = 剩余 684,153 篇待抽取；确认 PMID 无重复、摘要无空、输入/输出 schema 与训练及下游一致。task_plan 增补 Phase 10 详细小节（步骤/抉择/硬件预估）。待用户确认三项抉择（部署方式 Online vs Offline、本轮范围、压测方式）后执行：本地 filter_split 脚本 → 远程 vllm serve + 异步客户端 + 压测。
  - ✅ 用户拍板：① 部署 = Online Serving（vllm serve + 异步客户端）；② 本轮范围 = 本地数据准备 + 全部脚本（本地写并运行 filter_split，同时写好远程 serve/客户端/压测脚本待切远程执行）；③ 压测 = evalscope 合成 + 真实小样本 pilot 两者都做。开始落地。
- 2026-06-03 ✅ 本轮交付（scripts/vllm_inference/，5 文件，均通过语法检查）：
  - 01_filter_split.py（本地已跑）：流式 ijson 剔除 67,925 已提取 → 保留 684,153 篇，round-robin 写 20 片（各 34,207~34,208）到 data/vllm_inference/input_shards/，合计 1.19GB；manifest 计数校验一致。分片格式 {PMID,user_content}（user_content 已按训练方式压空白）。
  - 02_serve_vllm.sh：vllm serve merged（OpenAI 兼容，--enable-prefix-caching 复用公共 system 前缀、--disable-log-requests），参数全 env 覆盖；显式不带任何 thinking/reasoning 开关。
  - 03_extract_client.py：核心异步客户端。走 /v1/completions + 客户端 tokenizer 渲染（模板因式分解 PREFIX/SUFFIX，启动自检末尾=<|im_start|>assistant\n 否则退出），producer→input_q→N worker→result_q→单 writer 落盘；triples.jsonl 对齐既有 8 字段 schema，断点续跑(_state/done_pmids.txt)，失败/截断分账，吞吐外推（--limit 即 pilot，--gpu-hourly-cost 出费用）。
  - 04_perf_evalscope.sh：evalscope random 合成压测扫并发(8/16/32/64/128)，ignore_eos 量保守解码吞吐。
  - README.md：对齐铁律 + 6 步编排（本地分片→远程起服务→pilot→evalscope→全量→收尾）。
  - ⏭️ 下一步（需切远程，remote-server-ops）：上传分片 → 建 vllm_env 起服务 → pilot 量吞吐外推费用 → evalscope 调并发 → 全量跑。

- 2026-06-04 Phase 10 远程落地（医学集群 A100-80G / 项目 /root/ICKG）。
  - 环境踩坑链：最新 vllm 0.22(torch2.11/cu13) 与驱动 550(CUDA12.4) 不兼容 → 锁定 **vllm==0.8.5.post1 + torch2.6.0+cu124**（vllm_env, py3.12）。pip 改阿里云镜像(/root/.pip/pip.conf)。transformers 被装成 5.9 触发 vllm 调 `all_special_tokens_extended` 报错 → 降到 **4.51.3**。merged 目录缺 vocab.json/merges.txt，vllm 走 slow tokenizer 加载崩 → serve 用 **--tokenizer models/hf/Baichuan-M2-32B**（base 词表齐全，同一词表）。客户端 03 漏 argparse `--api-key` 已修并提交(0f621d7)。
  - pilot 实测(bf16, 单A100, 并发32, temp0)：**~0.42 篇/s**、GPU 98% 满载、KV cache 47,888 tok、**max_tokens4096+max_model_len12288 时 0% 截断**、~11 三元组/篇、JSON 100% 合法。对齐自检通过(末尾 <|im_start|>assistant
)。
  - 决策(用户)：①bf16 原样跑(质量优先，拒绝 int4)；②max_tokens4096+maxlen12288；③并发32(GPU已满)。成本 ~3,170-3,350 元/~19-20 天(7.01元/h)，磁盘无需扩(输出仅~2GB)。重训问题：**不需要**(老师M3的completion 8153含思考；学生纯答案~1000，2326是答案长度)。
  - 全量已在 tmux `vllm_extract` 启动 → data/vllm_inference/output/{triples,usage,failed,truncated}.jsonl + _state/done_pmids.txt（断点续跑）。服务在 tmux `vllm_serve`。

- 2026-06-04 ⚠️复读循环问题与根治（Phase 10）。
  - 现象：bf16 全量约 24% 文章「截断(全是恰好 max_tokens)或 json_parse_failed」，且 51/52 截断篇零产出。
  - 根因：贪心(temperature 0)在 vLLM 高并发下的「批次数值不确定性」→ 个别文章复读同一三元组刷到 max_tokens；隔离单测同篇时好时坏，实锤非确定性。复读请求还长期霸占有限 KV 槽位拖垮吞吐。
  - 采样实验：rep_penalty 能断复读但误伤召回(结构 token 被罚，13→7)；小温度 t0.1/0.5 偶尔仍复读；**没有采样参数能 100% 杜绝**。
  - 根治 = ①客户端加「残片打捞 salvage_objects + 按(head,head_type,relation,tail,tail_type)去重」：截断/复读输出也能抠出全部唯一三元组，failed 89→0、截断篇 23/23 全救回；②降 max_tokens 4096→2560：把复读浪费截短、KV 槽位更快释放，吞吐 0.40→0.46；temp 保持 0。已提交 351e813。
  - 决策(用户)：max_tokens=2560。清掉被污染的旧 output(369含24%坏数据+混入)，用新配置全量重启：tmux vllm_extract，temp0/2560/并发32/打捞去重 → 0.46篇/s≈17天/~2900元，failed=0、截断全救回。
  - 另：训练集答案 token 分布核验(05脚本)：中位633/p99 2152/max 3631，full>5120仅0.22%→训练目标几乎没被截断，不需重训。

- 2026-06-04 会话收尾（日志归档 + 计划落盘 + 提交）。
  - 本会话已完成日志归档到 log/vllm_inference_20260604/（conda_create、vllm_install、vllm_pilot1-4）；两个实时日志 vllm_serve.log / vllm_extract.log 进程仍在写、监控在用，暂留 log/ 根目录，全量跑完再归档。
  - 主全量稳定 ~0.49 篇/s（≈16 天）、failed=0、截断 ~10% 全被打捞救回；累计已完成约 6000 篇。
  - 本会话新增/改动并已提交：03（补 --api-key、残片打捞+5元组去重）、05（训练集答案长度核验）、06（截断篇补尾重抽+并集去重，待全量跑完执行）；计划三件套；远端 pip.conf 改阿里云、vllm_env 建好。

- 2026-06-04 余额不足，暂停全量推理待充值。停机点：已完成 85,970 / 684,153 篇（约 12.6%），累计约 99 万条三元组，failed=1，截断约 8576（10%，待 06 补尾）。已停 tmux vllm_extract 与 vllm_serve，GPU 已释放（显存 1MiB），两个实时日志已归档到 log/vllm_inference_20260604/。done_pmids.txt 已逐条落盘——充值并重启后：先起服务 02（MAX_MODEL_LEN=12288 + EXTRA_ARGS=--tokenizer base），再重跑客户端 03（temp0 / max_tokens2560 / 并发32）即自动跳过已完成、断点续跑。

- 2026-06-08 充值后恢复全量推理（质量优先）。
  - 用户问「GPU 显存没跑满能否榨干」：澄清显存已 95.7%（gpu_mem_util 0.95，= 62G 权重 + ~12G KV + 开销），GPU-Util 98% 算力已饱和，非浪费。
  - 实测 fp8 KV（--kv-cache-dtype fp8）把 12288 并发从 3.98x 提到 8.82x（约 2.3 倍，因解码是显存带宽瓶颈、本可近翻倍吞吐）；但用户选质量优先 → 不用 fp8（KV 量化有极小数值误差）。
  - 截断处理决策：不全局提 max_tokens（会拖慢剩余全部 60 万只为救 10%），保持 2560 跑快；最后用 06 仅对高产截断篇（如 ≥12 条）定向补尾。
  - 已用已验证配置（bf16 KV / gpu_mem_util 0.95 / max_model_len 12288 / base 词表 / temp0 / max_tokens 2560 / 并发 32）从 85,970 续跑，GPU 98% 满载。剩余约 59.8 万篇 ≈ 14 天 / ~2,400 元。

- 2026-06-15 客户端卡死 3.5 天事故 + 监工自愈。
  - 现象：客户端于 06-11 22:14 静默卡死（日志停更），vLLM 服务仍占显存空转、GPU 0%，到 06-15 才发现 → 约 83 小时空转、浪费约 580 元。非磁盘问题（22G 空闲）。进度停在 done=234222（34%）。
  - 根因：客户端某次异常让 writer 协程静默死掉（异常被未 await 的任务吞掉）→ result_q 塞满 → 所有 worker 卡在入队 → 进程不退也不干活、无报错。服务端正常（重启客户端后立刻 97% 满载续跑，证明是客户端侧死锁）。
  - 修复：新增 scripts/vllm_inference/run_extract_supervised.sh 监工——日志若 STALL 秒（默认 300）不增长即判定卡死、kill 客户端并自动重启续跑；done>=TOTAL 或某轮零进展才停；放 tmux vllm_extract。已从 234222 续跑、GPU 97%。
  - 剩余约 45 万篇 ≈ 10.6 天 / ~1790 元（0.49 篇/s，7.01 元/h）。后续监控看 done 数与 [sup] 行即可。

- 2026-06-24 自动接补尾编排 + 费用确认。进度 done=606242（88.6%）、三元组约 697 万、截断 61143、健康（0.49 篇/s，GPU 97%，监工正常）。
  - 费用测算（7.01 元/h，余额 891.43）：主推理剩余 77911 篇 ≈ 44h ≈ 310 元；全部补尾约 69k 篇（6144/temp0.5，~0.25 篇/s）≈ 77h ≈ 450–670 元；合计约 850 元 < 余额 → 大概率无需充值。用户另充 300 元（未即时到账，纯备用）。
  - 新增 scripts/vllm_inference/run_recover_after_main.sh 编排（tmux vllm_recover）：等主推理结束（done>=TOTAL 或 vllm_extract 会话退出）→ 监工式跑 06 --apply 全部补尾（卡死自愈）→ --merge-only 出最终 triples_merged.jsonl。可中断（kill vllm_recover + pkill 06）、可续跑（重启脚本，06 靠 recovered_pmids.txt 续）。
  - 中断/续跑约定：余额将耗尽时用户会让中断补尾；充值到账后重启 vllm_recover 即续。

- 2026-06-24 发布数据集与 adapter 到 Hugging Face（公开）。
  - 数据集 Siyu2Zhou/ICKG-immunology-triple-extraction-sft：train/val/test.jsonl(4500/250/250) + 中文 README（含格式/schema/19类实体/加载示例）。
  - 模型 Siyu2Zhou/Baichuan-M2-32B-QLoRA-immunology-triples：adapter(r16/alpha32, 537MB) + 中文 README（含 transformers+PEFT 与 vLLM 两种复现用法、对齐铁律） + Triple_prompt_v2_finetune.md + tokenizer；adapter_config 基座路径已改为 baichuan-inc/Baichuan-M2-32B。
  - 国内→HF 大文件/建仓 API 频繁超时：改用 hf_transfer + 重试循环解决（adapter 第2次重试成功）。token 仅用 HF_TOKEN 环境变量临时传、未持久化登录；已提醒用户轮换该 token。

- 2026-06-26 vLLM 三元组推理全流程完成（Phase 10 收官）。
  - 主推理：done=684149/684153（差 4 篇持续网络失败，可忽略）；triples.jsonl 累计 7,856,425 条三元组。06-26 03:13 主推理监工检测零进展正常退出，编排器自动接补尾（自动化链路跑通）。
  - 补尾：实测仅 0.04 篇/s、净增约 +0.3 条/篇，外推全部补尾 ~20 天/~3362 元、ROI 极差；用户决定停止补尾（已补 511/69068）。
  - 定稿：06 --merge-only 合并 → data/vllm_inference/output/triples_merged.jsonl，共 7,863,996 条三元组（2.6GB，含 511 篇补尾并集，其余截断篇保留原已打捞三元组）。
  - 已停 vLLM 服务、释放 GPU（1MiB）；待用户控制台停机止损。监控循环结束。Phase 10 完成。
