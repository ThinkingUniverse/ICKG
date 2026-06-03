# vLLM 推理：抽取剩余 ~684k 篇 PubMed 摘要的三元组

> 计划：`.planning/baichuan-qlora/`（Phase 10）。模型：`models/Baichuan-M2-32B-QLoRA-v1/merged`（远程，bf16，~62G）。

## 数据盘点（本地实测）
- 全量 752,078 篇 − 已提取 67,925（First 40,256 + Second 27,987，零交集）= **剩余 684,153 篇**。

## 🔴 对齐铁律（违反即废）
微调用的是「不带 thinking」的分布：推理 prompt 末尾必须是 `<|im_start|>assistant\n`。
- **绝不传 `thinking_mode`**（连 `thinking_mode='off'` 都会注入未训练的 `<think>`）。
- 因此客户端走 `/v1/completions`，自己用 tokenizer 渲染 prompt（启动时自检末尾，不符合即退出）；
  服务端 `02_serve_vllm.sh` **不要**加任何 reasoning/thinking 开关。
- system 提示词固定 `prompts/Triple_prompt_v2_finetune.md`；user = `title.strip()+空格+abstract.strip()` 压空白。

## 文件
| 文件 | 跑在哪 | 作用 |
|---|---|---|
| `01_filter_split.py` | 本地 | 剔除已提取 PMID，剩余文章 round-robin 分片成 `{PMID,user_content}` |
| `02_serve_vllm.sh` | 远程 | `vllm serve` merged（OpenAI 兼容，开前缀缓存） |
| `03_extract_client.py` | 远程 | 异步并发抽取，增量落盘，断点续跑，吞吐外推（`--limit` 即 pilot） |
| `04_perf_evalscope.sh` | 远程 | evalscope 合成压测，扫并发甜点 |

## 步骤

### 1. 本地：数据准备
```bash
python scripts/vllm_inference/01_filter_split.py --num-shards 20
# 产出 data/vllm_inference/input_shards/shard_*.jsonl + manifest.json
```
把 `data/vllm_inference/input_shards/` 上传到远程同路径（或在远程重跑 01）。

### 2. 远程：环境 + 起服务
```bash
conda create -n vllm_env python=3.12 -y && conda activate vllm_env
pip install vllm
tmux new -s vllm
bash scripts/vllm_inference/02_serve_vllm.sh         # 默认 8801；可 PORT=/MAX_MODEL_LEN= 覆盖
```

### 3. 远程：真实数据 pilot（先小样本量吞吐，再外推费用）
```bash
conda activate vllm_env   # 客户端只用 aiohttp + transformers（随 vllm 已装）
python scripts/vllm_inference/03_extract_client.py \
  --limit 2000 --concurrency 128 \
  --gpu-hourly-cost <你的GPU元/小时> \
  --output-dir data/vllm_inference/pilot
# 末尾会打印 篇/s、out-tok/s，并按 684153 外推总耗时与费用 → 据此决定充值
```

### 4. 远程：evalscope 合成压测（调并发甜点，可选并行做）
```bash
conda create -n evalscope python=3.12 -y && conda activate evalscope
pip install 'evalscope[perf]' -U
bash scripts/vllm_inference/04_perf_evalscope.sh     # 对比 8/16/32/64/128 并发的吞吐与延迟
```
用甜点并发回填 `02` 的 `MAX_NUM_SEQS` 与 `03` 的 `--concurrency`。

### 5. 远程：正式全量
```bash
nohup python scripts/vllm_inference/03_extract_client.py \
  --concurrency <甜点> --output-dir data/vllm_inference/output \
  > log/vllm_extract.log 2>&1 &
# 断点续跑：中断后重跑同命令即可（_state/done_pmids.txt 自动跳过已完成）
```

### 6. 收尾
- 产物 `data/vllm_inference/output/triples.jsonl`（每行一条三元组，对齐既有 schema）下载回本地。
- 核对 `failed.jsonl` / `truncated.jsonl`：截断的可调大 `--max-tokens` 重跑；失败的重跑即续。
- 并入实体对齐 / KG 构建下游（`scripts/Entity_alignment`）。

## 部署选型说明（为什么 Online）
同引擎连续批处理下 Online 与 Offline 吞吐等价；选 Online 因为：① evalscope 压测需 HTTP 端点；
② 服务与客户端解耦 + 断点续跑，对多小时长任务更稳健；③ 前缀缓存复用 1,919 tok 的公共 system 提示词。
