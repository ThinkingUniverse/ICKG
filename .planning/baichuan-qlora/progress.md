# Progress Log — Baichuan-M2-32B QLoRA

> 追加式日志，最新在底部；每完成一步追加一条。

- 2026-05-14 制定实施方案（Fine_tuning_Plan）
- 2026-05-14~18 本地数据处理 01–05 完成，sampling_stats 达标（increases 30.00% / associated_with 51.44%）；提示词精简版 1,919 tok；train/val/test 切分完成
- 2026-05-15 服务器操作手册初稿
- 2026-05-18 烟测 20 步通过（显存 64.6G，loss 0.124）；踩坑 3 类报错并修复（torch / SwanLab / trl 模板）
- 2026-05-28 服务器增补：vda1 扩到 128G；env ickg 版本锁定；评估报告完成，给出开训前 checklist
- 2026-06-01 用 planning-with-files 建立 .planning/baichuan-qlora/ 状态层（三件套），链接现有文档
- （下一条）待：完成开训前 checklist → tmux 启动 3 epoch 训练
