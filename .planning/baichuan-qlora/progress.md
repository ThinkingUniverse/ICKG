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
