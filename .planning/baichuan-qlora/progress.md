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
