# 服务器训练操作手册 — Baichuan-M2-32B QLoRA

> 制定日期：2026-05-15
> 目标硬件：1× A100 SXM4 80GB / 24 核 / 48 GB RAM / 300 GB SSD
> 服务器：Ubuntu 22.04.1 LTS  •  IP `8.130.9.186`  •  端口 `25070`  •  用户 `root`  •  密码 `xxx`

---

## 0. 总览（实测数据 2026-05-18 更新）

| 阶段                         | 实测/预估耗时 | 备注                                                                |
| ---------------------------- | ------------- | ------------------------------------------------------------------- |
| 系统准备 + Miniconda         | 10 分钟       | 一次性                                                              |
| 克隆仓库 + 装依赖            | 15-25 分钟    | 含 flash-attn 编译/下载                                             |
| 下载 Baichuan-M2-32B (~65GB) | 30-60 分钟    | 走 hf-mirror，国内带宽决定                                          |
| **烟测训练 20 步**           | **20 分 37 秒**（实测） | 50 train + 20 eval 样本，每 step ≈ 61 秒                |
| **正式训练 3 epoch（质量优先）** | **~14.3 小时**（实测推算） | 4500 样本 / bsz=2 / grad_accum=8 → 843 步 × 61s ≈ ¥100 |
| 合并 LoRA → bf16 完整权重    | 10-15 分钟    | A100 80GB 上完成，约 ¥2                                              |
| 在 test.jsonl 上做业务指标评估 | 5-10 分钟     | 250 条样本，~¥1-2                                                   |
| 下载结果到本地               | 10-30 分钟    | merged 权重 ~65GB                                                   |

### 烟测实测要点

- **GPU 显存峰值 64.6 GB / 80 GB**（用量 79%，安全）
- **GPU 利用率 99%，功耗 423W**（满载）
- 烟测 20 步训练 loss 从 0.152 降到 0.097，eval_loss 0.1243（数据集太小不具备参考意义，仅证管道通）
- 全量训练完整 1 epoch ≈ 281 steps × 61s = 17,141s ≈ **4 小时 45 分钟**

---

## 1. 本地端：推送代码到 GitHub

在本地 PowerShell（`C:\Users\Administrator\Desktop\ICKG`）执行：

```powershell
# 1.1 确认 .gitignore 已放开 6 个训练文件
git ls-files --others --exclude-standard data/Fine_tuning_dataset/training_ready/v1/
# 应输出：train.jsonl / val.jsonl / test.jsonl / sft_dataset.jsonl / sampled_5000_pmids.txt / sampling_stats.json

# 1.2 添加并提交（避免 git add -A 误带凭证文件）
git add .gitignore prompts/Triple_prompt_v2_finetune.md src/Fine_tuning/ Plan/20260514/Baichuan-M2-32B_QLoRA_Fine_tuning_Plan.md `
        data/Fine_tuning_dataset/training_ready/v1/train.jsonl `
        data/Fine_tuning_dataset/training_ready/v1/val.jsonl `
        data/Fine_tuning_dataset/training_ready/v1/test.jsonl `
        data/Fine_tuning_dataset/training_ready/v1/sft_dataset.jsonl `
        data/Fine_tuning_dataset/training_ready/v1/sampled_5000_pmids.txt `
        data/Fine_tuning_dataset/training_ready/v1/sampling_stats.json

git status                                  # 核对：不应出现 pmid_to_abstract.jsonl 或 .Server_Operation_Manual.md
git commit -m "feat: add QLoRA fine-tuning pipeline + training data v1"
git push origin main
```

---

## 2. SSH 登录服务器

### 2.1 推荐方式：VSCode Remote-SSH

本机已用 VSCode + Remote-SSH 远程开发，建议直接用这套：

1. VSCode 打开命令面板 (`Ctrl+Shift+P`) → `Remote-SSH: Open SSH Configuration File...` → 选 `C:\Users\Administrator\.ssh\config`，添加：
   ```
   Host ickg-server
       HostName 8.130.9.186
       Port 25070
       User root
   ```
2. 命令面板 → `Remote-SSH: Connect to Host...` → 选 `ickg-server` → 输入服务器密码（勿写入文档，按需临时输入）
3. 连上后 `File → Open Folder → /root/ICKG`（项目克隆完之后），整个项目在远端，本地编辑同步执行
4. **端口转发自动化**：VSCode 检测到服务器上有 6006 / 8080 等端口监听时会自动转发到本地，无需手动 `ssh -L`。也可以在 `PORTS` 面板手动 forward
5. **集成终端**：`Ctrl+\`` 打开远端终端，所有后续 bash 命令直接在 VSCode 终端里跑

### 2.2 备用方式：原生 SSH

在本地 PowerShell 执行：

```powershell
ssh -p 25070 root@8.130.9.186
# 密码：xxx
```

> 提示：如果想免密，可执行 `ssh-keygen` 后 `ssh-copy-id -p 25070 root@8.130.9.186`（本步可选）。

登录成功后，所有后续命令都在服务器上执行。

---

## 3. 系统检查（确认环境）

```bash
# 3.1 当前位置
cd /root && pwd                              # 应输出 /root

# 3.2 操作系统、内核
uname -a
cat /etc/os-release | head -2

# 3.3 磁盘空间（重点：/ 或 /root 至少 250GB 可用）
df -h /

# 3.4 内存（应看到 ~48GB total）
free -h

# 3.5 CPU 核数（应看到 24）
nproc

# 3.6 GPU（应看到 A100 80GB）
nvidia-smi
# 关注：CUDA Version (右上)、Memory (80GB)、Driver Version

# 3.7 网络
curl -I https://hf-mirror.com                # 应返回 200/301
curl -I https://github.com                   # 用于 git clone
```

如果磁盘不够 250GB 或 GPU 不是 A100 80GB，**先停下来联系厂商**，别开始下面的步骤。

---

## 3.5 磁盘扩容（当 `df -h /` 不足时）

### 3.5.1 典型现象与诊断

```bash
df -h /
# Filesystem      Size  Used Avail Use% Mounted on
# /dev/vda1        32G  3.5G   27G  12% /        ← 根分区只有 32G

lsblk
# vda    252:0    0  128G  0 disk          ← 磁盘 128G
# `-vda1 252:1    0   32G  0 part /         ← 分区只到 32G，剩 96G 未划分
# vdb    252:16   0   64G  1 disk           ← 另一块独立磁盘 64G，未挂载
```

**原因**：云厂商通常把根分区设置为较小的初始值（32G），剩余空间需要手动 `growpart` 扩展；额外的数据盘 `vdb` 默认不会自动挂载。

### 3.5.2 扩展 vda1 占用 vda 全部空间（32G → 128G）

```bash
# 装 growpart 工具
apt-get update && apt-get install -y cloud-guest-utils

# 扩展分区表：把 vda1 拉到 vda 的末尾（注意 vda 与 1 之间是空格，不是斜杠）
growpart /dev/vda 1

# 在线扩容文件系统（ext4）
resize2fs /dev/vda1
# 如果是 xfs：xfs_growfs /

df -h /
# 应看到 Size ≈ 125G
```

### 3.5.3 处理 vdb 64G 独立数据盘（推荐挂作 HF 缓存）

vdb 是 SCSI 上的独立块设备，**不能简单"扩展到 vda1"** — 需要 LVM 才能合卷，操作复杂且风险高。简单做法：挂作独立目录，把模型缓存（~65GB）放上面，给 vda1 留空间放 merged 权重与 checkpoints。

```bash
# 看 vdb 是否已格式化（如果输出含 "data" 字样则未格式化）
file -s /dev/vdb

# 没格式化的话先建 ext4
mkfs.ext4 -F /dev/vdb

# 挂作 HF 缓存目录（与 train_config.yaml 的 HF_HOME 对齐）
mkdir -p /root/ICKG/models/hf
mount /dev/vdb /root/ICKG/models/hf

# 写入 /etc/fstab 持久化，重启不丢
UUID=$(blkid -s UUID -o value /dev/vdb)
echo "UUID=$UUID /root/ICKG/models/hf ext4 defaults,nofail 0 2" >> /etc/fstab

df -h /root/ICKG/models/hf
# 应看到 Size ≈ 63G  Avail ≈ 59G
```

⚠️ **注意 64G 略小于 65GB 模型**：Baichuan-M2-32B safetensors 实际 60-66 GB，加文件系统开销，vdb 可能正好够也可能差 1-2 GB。**优先方案**：等下周厂商把 vda 扩到 300G 之后，直接用 vda1（一切放根分区，最简单）。本周如果非要先跑：把 base 放 vdb，merged 放 vda1（120G+ 充裕）。

### 3.5.4 下周厂商把 vda 升到 300G 后

云控制台扩容后磁盘自动变大，但分区不会自动跟着大。再跑一次：

```bash
growpart /dev/vda 1
resize2fs /dev/vda1
df -h /
# 此时 Size ≈ 295G，单根分区即可放下所有产物
```

如果当时 vdb 已经在用，可以视情况：（a）保留 vdb 不动；（b）卸载 vdb 把数据迁回 vda1（`umount` + `rm /etc/fstab` 对应行 + `cp -r` 数据）。

---

## 4. 安装 Miniconda

```bash
cd /root

# 4.1 下载 Miniconda（国内镜像）
wget https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py310_24.7.1-0-Linux-x86_64.sh -O miniconda_installer.sh

# 4.2 静默安装到 /root/miniconda3
bash miniconda_installer.sh -b -p /root/miniconda3
rm miniconda_installer.sh

# 4.3 初始化 shell
/root/miniconda3/bin/conda init bash
source ~/.bashrc                             # 重新加载，使 conda 命令可用

# 4.4 关闭默认进入 base 环境（可选，让 shell 干净）
conda config --set auto_activate_base false

# 4.5 配置国内镜像源（清华），加速 conda install
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free
conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge
conda config --set show_channel_urls yes
```

---

## 5. 创建虚拟环境（Python 3.10）

> **为什么选 3.10**：所有依赖（torch / transformers / peft / trl / bitsandbytes）官方都稳定支持 3.10；性能优于 3.9；比 3.11/3.12 与各库的兼容性更稳。本项目本地用 3.9，服务器升到 3.10 不会带来兼容问题（脚本里没有 3.10+ 专有语法）。

```bash
conda create -n ickg python=3.10 -y
conda activate ickg                          # 之后所有 pip 都装在这个 env

python --version                             # 应输出 Python 3.10.x
which python                                 # 应输出 /root/miniconda3/envs/ickg/bin/python
```

---

## 6. 克隆仓库

```bash
cd /root

# 6.1 克隆项目（替换为你的实际 GitHub 仓库 URL；如果是私库需要 PAT）
git clone https://github.com/<your_account>/ICKG.git
# 私库 https + PAT：git clone https://<PAT>@github.com/<account>/ICKG.git

cd ICKG
ls                                           # 应看到 src/ prompts/ data/ Plan/ 等

# 6.2 核对训练数据已就位
ls -lh data/Fine_tuning_dataset/training_ready/v1/
# 应看到：train.jsonl (~53MB) / val.jsonl / test.jsonl / sft_dataset.jsonl / sampled_5000_pmids.txt / sampling_stats.json
```

---

## 7. 安装 Python 依赖

```bash
# 7.1 配置 pip 国内镜像
mkdir -p ~/.pip
cat > ~/.pip/pip.conf <<'EOF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
extra-index-url = https://download.pytorch.org/whl/cu121
EOF

# 7.2 升级 pip
pip install --upgrade pip

# 7.3 安装 PyTorch 2.4.0 + CUDA 12.1（A100 完美兼容）
pip install torch==2.4.0 --index-url https://download.pytorch.org/whl/cu121

# 7.4 验证 torch + CUDA
python -c "import torch; print('torch:', torch.__version__, 'cuda:', torch.cuda.is_available(), 'device:', torch.cuda.get_device_name(0))"
# 应输出：torch: 2.4.0+cu121  cuda: True  device: NVIDIA A100-SXM4-80GB
```

> **关于"驱动 CUDA 12.4 / torch cu121 / flash-attn cu123" 三个版本不一致的问题**
>
> 这是 **CUDA 的标准前向兼容机制**，不会有问题，原因：
>
> 1. **`nvidia-smi` 显示的 CUDA Version 是驱动支持的最高 CUDA Toolkit 版本**（12.4），不是实际运行版本。任何 `<= 12.4` 编译的 CUDA 程序都能在这个驱动上跑。
> 2. **PyTorch cu121 wheel** 内置 CUDA 12.1 的运行时库（libcudart 等），不依赖系统 CUDA toolkit。装在 12.4 驱动上 → ✅ 兼容。
> 3. **flash-attn cu123 wheel** 内置 CUDA 12.3 运行时库。装在 12.4 驱动上 → ✅ 兼容。
> 4. **torch 与 flash-attn 之间的 ABI 兼容**：你装的是 `+cu123torch2.4cxx11abiFALSE` 这个 wheel，明确标了 torch 2.4 + cxx11abi=False，与上面装的 `torch==2.4.0+cu121`（默认也是 cxx11abi=False）完全匹配。
>
> 简言之：**只要驱动 CUDA Version >= 各 wheel 内置的 CUDA 运行时版本，就稳**。你的栈是 driver 12.4 ≥ torch 12.1 ≥ flash-attn 12.3，全部满足，后期不会报错。
>
> 验证一下（可选）：
>
> ```bash
> python -c "import torch, flash_attn; \
>   import flash_attn_2_cuda as fa; \
>   x = torch.randn(2, 4, 8, 16, dtype=torch.bfloat16, device='cuda'); \
>   from flash_attn import flash_attn_func; \
>   print('FA2 fwd OK, output shape:', flash_attn_func(x, x, x).shape)"
> # 能跑出 shape 即真正调通了 FA2 内核（不只是 import 通过）
> ```

```bash
# 7.5 安装核心训练栈
# 注意：trl 必须 >= 0.16（用 SFTConfig.max_length 与 assistant_only_loss 两个新参数）
pip install \
  "transformers>=4.45.0" \
  "peft>=0.13.0" \
  "trl>=0.16.0" \
  "accelerate>=0.34.0" \
  "datasets>=2.21.0" \
  "bitsandbytes>=0.43.3" \
  "swanlab>=0.4.0" \
  "tensorboard>=2.17.0" \
  "pyyaml>=6.0" \
  "scipy>=1.13.0" \
  "sentencepiece>=0.2.0"

# 7.6 验证 bitsandbytes（最容易出问题的依赖）
python -m bitsandbytes
# 应输出 "PyTorch installed: True" 和 "Library not detected: False"
```

### 7.7 安装 Flash Attention 2（可选但强烈推荐）

A100 + 长序列开启 FA2 可省 ~30% 显存、加速 1.5-2x。

```bash
# 优先尝试预编译 wheel（最快）
pip install flash-attn==2.6.3 --no-build-isolation

# 如果上面失败（说明在源码编译），改用下面这个明确的预编译 wheel 链接：
# 适配 Python 3.10 / torch 2.4 / cu121 / 不要 abi3
pip install https://github.com/Dao-AILab/flash-attention/releases/download/v2.6.3/flash_attn-2.6.3+cu123torch2.4cxx11abiFALSE-cp310-cp310-linux_x86_64.whl

# 验证
python -c "import flash_attn; print('flash-attn:', flash_attn.__version__)"
```

**如果 FA2 装不上**：编辑 `src/Fine_tuning/configs/train_config.yaml`，把 `attn_implementation: "flash_attention_2"` 改为 `attn_implementation: null`，模型走默认 SDPA / eager 注意力，性能略降但能跑。

---

## 8. SwanLab 登录

```bash
swanlab login
# 粘贴你自己的 SwanLab API Key（不要把真实 Key 写入仓库或日志）
# 成功后 key 存到 ~/.netrc，不会再问
```

---

## 9. 下载基础模型（独立步骤）

把模型下载与训练**分开**，便于：

- 提前确认磁盘 / 网络
- 训练失败重试时不必重新下载

```bash
# 9.1 设置 HF 镜像与缓存路径（也写到 ~/.bashrc 持久化，可选）
echo 'conda activate ickg' >> ~/.bashrc
echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.bashrc
echo 'export HF_HOME=/root/ICKG/models/hf' >> ~/.bashrc
source ~/.bashrc
# export HF_ENDPOINT=https://hf-mirror.com
# export HF_HOME=/root/ICKG/models/hf
mkdir -p $HF_HOME

# 9.2 下载 Baichuan-M2-32B 的所有权重 + tokenizer（约 65GB）
hf auth login
# 粘贴你自己的 Hugging Face Token（示例：hf_xxx；不要提交到 Git）
git config --global credential.helper store
hf download baichuan-inc/Baichuan-M2-32B \
  --local-dir $HF_HOME/Baichuan-M2-32B \
  --include '*'
# 中途断网可重跑同命令，会从断点续传

# 9.3 核对大小
du -sh $HF_HOME/Baichuan-M2-32B               # 应在 60-66 GB
df -h /                                       # 看剩余空间，至少 130 GB 可用以便后续 merge
```

> **小坑**：`from_pretrained` 默认按"仓库名"找缓存路径。如果直接传 `baichuan-inc/Baichuan-M2-32B`，HF 会去 `$HF_HOME/hub/models--baichuan-inc--Baichuan-M2-32B/` 找而不是上面的 `--local-dir`。两种解决：
>
> - **推荐**：把 `train_config.yaml` 里的 `model.name_or_path` 改成本地路径 `/root/ICKG/models/hf/Baichuan-M2-32B`（不依赖 HF 缓存机制）
> - 或：删除 `--local-dir` 参数让 HF 用标准缓存目录，并把 `HF_HUB_CACHE` 也指向 `$HF_HOME/hub`

```bash
# 9.4 修改 train_config.yaml 让 model.name_or_path 指向本地路径（推荐做法）
sed -i 's|name_or_path: "baichuan-inc/Baichuan-M2-32B"|name_or_path: "/root/ICKG/models/hf/Baichuan-M2-32B"|' \
  src/Fine_tuning/configs/train_config.yaml

grep name_or_path src/Fine_tuning/configs/train_config.yaml
# 应输出：name_or_path: "/root/ICKG/models/hf/Baichuan-M2-32B"
```

---

## 10. 烟测：跑通管道（20 步）

正式开训前先跑小规模，确认无 OOM、loss 在下降。

```bash
cd /root/ICKG

python src/Fine_tuning/training/train_qlora.py \
  --config src/Fine_tuning/configs/train_config.yaml \
  --max-train-samples 50 \
  --max-eval-samples 20 \
  --max-steps 20
```

**烟测预期**：

1. 看到 `[量化]`, `[模型] 加载 ...`, `[LoRA] r=16 ...`, `[SwanLab] 已初始化 ...` 等启动日志
2. 进入训练后每 10 步打印一次 loss，应看到 loss 从 ~2-3 下降
3. nvidia-smi 另开终端看，显存应稳定在 50-65 GB
4. 20 步后自动结束，**无 OOM** 即成功
5. SwanLab dashboard 应看到这个烟测 run 的 loss 曲线

**烟测失败排查**：

| 现象                        | 原因                        | 解决                                                                                                    |
| --------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------- |
| `CUDA out of memory`      | max_seq_length / batch 过大 | 把 max_seq 5120 → 4096，或 bsz 2 → 1                                                                  |
| `flash_attn not found`    | FA2 未安装                  | 改 attn_implementation 为 null                                                                          |
| `Killed` (无报错直接退出) | host RAM 不够               | 设置 swap:`fallocate -l 16G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile` |
| Loss 不降 / NaN             | lr 太大或精度问题           | 把 lr 1e-4 → 5e-5                                                                                      |

---

## 11. 正式训练（3 epoch）

### 11.0 清理烟测残留（**必做**）

烟测会留下 `adapter/`（会被覆盖，无影响）和 `checkpoints/checkpoint-*`（**不会**被 `save_total_limit` 清理，可能让 `load_best_model_at_end` 找错 checkpoint）。**正式训练前先清理**：

```bash
rm -rf /root/ICKG/models/Baichuan-M2-32B-QLoRA-v1/adapter
rm -rf /root/ICKG/models/Baichuan-M2-32B-QLoRA-v1/checkpoints
# 若 SwanLab 离线日志也想清，加：rm -rf /root/ICKG/swanlog
```

烟测通过后启动正式训练。建议用 `tmux` 防止 SSH 断开导致训练中止。

```bash
# 11.1 启动 tmux 会话
tmux new -s train

# 11.2 在 tmux 里启动训练
cd /root/ICKG
conda activate ickg
python src/Fine_tuning/training/train_qlora.py \
  --config src/Fine_tuning/configs/train_config.yaml \
  2>&1 | tee log/Fine_tuning/train_$(date +%Y%m%d_%H%M%S).log

# 11.3 detach（不停止训练）：按 Ctrl+B 再按 D
# 11.4 重新连接：tmux attach -t train
# 11.5 终止训练：tmux kill-session -t train
```

**实测耗时**（基于 2026-05-18 烟测推算，61s/step）：

| epoch 数 | 优化器步数 | 预计耗时 | 预计费用（¥6.96/h） | 适用场景 |
|---:|---:|---:|---:|---|
| 1 | 281 | ~4h 45min | ¥33 | 不足，欠拟合风险 |
| 2 | 562 | ~9h 30min | ¥66 | 省钱方案，可能 loss 未充分下降 |
| **3** | **843** | **~14h 20min** | **¥100** | **质量优先（默认 yaml 配置）** ✅ |

> 已配置 `load_best_model_at_end: true` + `metric_for_best_model: eval_loss`，即使第 3 epoch 末段过拟合，Trainer 会自动保存 eval_loss 最低的 checkpoint，不会因为多跑而损失质量。

**直接启动正式训练**（yaml 已是 3 epoch，无需任何修改）：

```bash
python src/Fine_tuning/training/train_qlora.py \
  --config src/Fine_tuning/configs/train_config.yaml
```

---

## 12. 训练监控

### 12.1 SwanLab Web Dashboard（推荐）

打开浏览器访问 `https://swanlab.cn/@zhousy/ICKG-Baichuan-M2-32B-QLoRA`，实时看 loss / lr / grad_norm 曲线。

### 12.2 TensorBoard 本地查看（SSH 端口转发）

新开本地 PowerShell：

```powershell
# 把服务器 6006 端口映射到本地 6006
ssh -p 25070 -N -L 6006:localhost:6006 root@8.130.9.186
```

服务器 tmux 新窗（Ctrl+B 然后 C）：

```bash
cd /root/ICKG
conda activate ickg
tensorboard --logdir log/Fine_tuning/tensorboard --port 6006 --host 0.0.0.0
```

浏览器打开 `http://localhost:6006`。

### 12.3 GPU 实时占用

```bash
watch -n 2 nvidia-smi
```

---

## 13. 合并 LoRA → 完整权重 + 推理速查

训练结束后，把 LoRA adapter 合并回基础模型得到一个独立的 bfloat16 完整权重，便于后续推理直接 `from_pretrained` 加载。

```bash
cd /root/ICKG
conda activate ickg

# 13.1 合并 + 在 test.jsonl 前 5 条上做推理 sanity check（一气呵成）
python src/Fine_tuning/training/merge_lora.py \
  --config src/Fine_tuning/configs/train_config.yaml \
  --device auto \
  --test-after-merge 5

# 输出在 models/Baichuan-M2-32B-QLoRA-v1/merged/
du -sh models/Baichuan-M2-32B-QLoRA-v1/merged/
# 应在 60-66 GB
```

### 13.2 推理速查的含义

`--test-after-merge 5` 会在 merge 完成后，**用刚合并好的 bf16 模型**对 `test.jsonl` 前 5 条做生成，并打印：

- USER 输入（前 200 字）—— title + abstract
- GROUND-TRUTH（前 500 字）—— 训练数据里 API 抽出的三元组 JSON
- MODEL 输出（前 500 字）—— 微调模型的预测
- JSON 合法性速查 ✅/⚠️/❌ + 抽出三元组条数

注意这只是**人工 sanity check**：5 条样本不足以做严格评估，但够看模型有没有正确学到 JSON 格式、关系类型、实体类型等基本要素。如果发现：
- ❌ JSON 解析失败比例高 → 输出格式没学好，需要检查训练数据 / 训练步数
- ✅ 但输出关系类型很多不在预定义集合 → 提示词压缩可能丢了关系信息
- ✅ 输出与 ground-truth 差异大但 JSON 合法 → 正常的"多解"，需要正式评估才能判断

### 13.3 备选用法

```bash
# 只合并不推理（最快，最省钱）
python src/Fine_tuning/training/merge_lora.py \
  --config src/Fine_tuning/configs/train_config.yaml --device auto

# 多看几条样本（如 10 条）
python src/Fine_tuning/training/merge_lora.py \
  --config src/Fine_tuning/configs/train_config.yaml --device auto \
  --test-after-merge 10
```

---

## 14. 下载结果到本地

在本地 PowerShell：

```powershell
# 14.1 LoRA adapter（小，~250MB）
scp -P 25070 -r root@8.130.9.186:/root/ICKG/models/Baichuan-M2-32B-QLoRA-v1/adapter `
    C:\Users\Administrator\Desktop\ICKG\models\Baichuan-M2-32B-QLoRA-v1\

# 14.2 训练日志（TensorBoard 离线缓存）
scp -P 25070 -r root@8.130.9.186:/root/ICKG/log/Fine_tuning `
    C:\Users\Administrator\Desktop\ICKG\log\

# 14.3 合并后完整权重（~65GB；可选，本地没空间可暂不下载）
scp -P 25070 -r root@8.130.9.186:/root/ICKG/models/Baichuan-M2-32B-QLoRA-v1/merged `
    C:\Users\Administrator\Desktop\ICKG\models\Baichuan-M2-32B-QLoRA-v1\
```

---

## 15. 清理服务器

```bash
# 15.1 如果只想保留 merged，删 base 与 checkpoints
rm -rf /root/ICKG/models/hf/Baichuan-M2-32B    # 删 base，腾出 ~65GB
rm -rf /root/ICKG/models/Baichuan-M2-32B-QLoRA-v1/checkpoints   # 删训练中 checkpoints

# 15.2 销毁实例前再 df -h /
df -h /
```

---

## 16. 故障排查速查

### 16.1 烟测时已碰到并已修复的三类问题（仓库 `error/` 有完整复盘）

| 错误 | 根因 | 修复 | 详细复盘 |
|---|---|---|---|
| `infer_schema(func): Parameter input has unsupported type torch.Tensor` | torch 2.3/2.4 不识别新版 transformers 的字符串注解 `'torch.Tensor'` | torch 升到 2.5+ cu124：`pip install --upgrade torch --index-url https://download.pytorch.org/whl/cu124` | [error/torch_transformers_custom_op_schema_mismatch/README.md](../../error/torch_transformers_custom_op_schema_mismatch/README.md) |
| `KeyError: 'max_seq_length'` 在 `maybe_init_swanlab` | yaml 已改 `max_length` 但 SwanLab init 漏改硬编码 | `train_qlora.py` 同步加 `.get('max_length') or .get('max_seq_length')` 兼容回退 | [error/swanlab_init_max_seq_length_keyerror/README.md](../../error/swanlab_init_max_seq_length_keyerror/README.md) |
| `ValueError: chat template is not training-compatible` | trl 0.16+ `assistant_only_loss` 需 `{% generation %}` 标记且模板"前缀保留"；Baichuan-M2 官方模板有 `last_query_index` 反向扫描和 think-wrapping 破坏前缀保留 | 新增 [`baichuan_m2_training_template.jinja`](../../src/Fine_tuning/training/baichuan_m2_training_template.jinja)，训练前覆盖 / 保存前还原 | [error/trl_assistant_only_loss_chat_template/README.md](../../error/trl_assistant_only_loss_chat_template/README.md) |

### 16.2 一般故障排查表

| 现象                                 | 排查方向                                                                                                      |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| 训练第一步就 OOM                     | `max_length` 太大 → 改回 4096                                                                              |
| 中途 OOM（如某条 long sample）       | 同上；或 `bsz=2 → 1`，`grad_accum=8 → 16` 保持有效 batch                                                |
| 训练速度异常慢 (<0.3 it/s)           | 检查是否 FA2 没生效（看启动日志 attn_implementation 字样）；或数据加载瓶颈（提高 `dataloader_num_workers`） |
| SwanLab 上传失败                     | 检查 `swanlab login` 是否成功；改 `swanlab.mode` 为 `local` 跑离线                                      |
| `bitsandbytes` 报 libcudart 找不到 | `export LD_LIBRARY_PATH=/root/miniconda3/envs/ickg/lib:$LD_LIBRARY_PATH`                                    |
| host RAM OOM（Killed）               | 加 swap：`fallocate -l 16G /swapfile && mkswap /swapfile && swapon /swapfile`                               |
| 模型下载断（hf-mirror 抽风）         | 重跑 `huggingface-cli download` 命令，支持断点续传                                                          |

---

## 17. 一键脚本（可选 — 让 11 节训练之前的所有步骤合一）

把 4-9 节打包成 `setup_server.sh`，下次换机器或重新初始化时一键跑：

```bash
cat > /root/setup_server.sh <<'EOF'
#!/bin/bash
set -e
cd /root
# Miniconda
[ ! -d /root/miniconda3 ] && wget -q https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-py310_24.7.1-0-Linux-x86_64.sh -O mc.sh && bash mc.sh -b -p /root/miniconda3 && rm mc.sh
source /root/miniconda3/etc/profile.d/conda.sh
# Env
conda env list | grep -q ickg || conda create -n ickg python=3.10 -y
conda activate ickg
# Pip mirror
mkdir -p ~/.pip && cat > ~/.pip/pip.conf <<EOL
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
extra-index-url = https://download.pytorch.org/whl/cu121
EOL
# Deps
pip install --upgrade pip
pip install torch==2.4.0 --index-url https://download.pytorch.org/whl/cu121
pip install "transformers>=4.45.0" "peft>=0.13.0" "trl>=0.16.0" "accelerate>=0.34.0" \
            "datasets>=2.21.0" "bitsandbytes>=0.43.3" "swanlab>=0.4.0" \
            "tensorboard>=2.17.0" "pyyaml>=6.0" "scipy>=1.13.0" "sentencepiece>=0.2.0"
echo "[完成] 基础环境已就绪。后续执行 flash-attn 安装、swanlab login、模型下载、训练。"
EOF
chmod +x /root/setup_server.sh
```

---

完。
