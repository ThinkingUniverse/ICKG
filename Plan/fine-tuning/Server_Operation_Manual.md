# 服务器训练操作手册 — Baichuan-M2-32B QLoRA

> 制定日期：2026-05-15  •  最近一次更新：2026-05-28
> 目标硬件：1× A100-SXM4-80GB (driver 550.163.01 / CUDA 12.4) / 24 vCPU / 47 GB RAM
> 系统盘：`/dev/vda1` 128 GB（已扩容，2026-05-28 状态：已用 80 G、可用 41 G）；数据盘 `/dev/vdb` 64 GB 未挂载（计划扩到 300 G 暂未执行）
> 服务器：Ubuntu 22.04.1 LTS  •  IP `8.130.9.186`  •  端口 `25070`  •  用户 `root`  •  SSH 别名 `医学集群`
> 当前 conda env：`ickg` (Python 3.10.20)  •  关键版本：torch 2.6.0+cu124 / transformers 5.8.1 / peft 0.19.1 / accelerate 1.13.0 / bitsandbytes 0.49.2 / trl 1.4.0 / flash-attn 2.6.3 / swanlab 0.7.18

---

## 0. 总览（实测数据 2026-05-18 更新，2026-05-28 增补服务器现状）

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

> **2026-05-28 服务器现状（实测）**：
> - `/dev/vda1` 已扩到 **128 G**（系统盘根分区，已用 80 G、可用 41 G）—— 当前节点 §3.5.2 的 `growpart` + `resize2fs` 已完成，**无需重复执行**。
> - `/dev/vdb` **64 G** 块设备，**未挂载**（用户决定暂时不动；该盘标记为 RO，需重新格式化才可写）。
> - 厂商承诺把 vda 扩到 **300 G** 的方案 **尚未执行**；本周内训练（base 模型 63 G + adapter 250 MB + merged 65 G ≈ 130 G）刚好顶在 vda1 128 G 上沿，**先不下载 merged 到本地之前，注意监控 `df -h /`**。
> - 若中途空间紧张，先按 §15.1 删 base 或 checkpoints 中间产物；非紧急情况下不要去动 vdb（避免误操作）。

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

# 6.1 克隆项目（公开仓库）
git clone https://github.com/ThinkingUniverse/ICKG.git
# 若为私库 + PAT：git clone https://<PAT>@github.com/ThinkingUniverse/ICKG.git

cd ICKG
git log --oneline -5                         # 确认拉到的是最新 main
git status                                   # 应为 clean
ls                                           # 应看到 src/ prompts/ data/ Plan/ 等

# 6.2 核对训练数据已就位
ls -lh data/Fine_tuning_dataset/training_ready/v1/
# 应看到：train.jsonl (~53MB) / val.jsonl / test.jsonl / sft_dataset.jsonl / sampled_5000_pmids.txt / sampling_stats.json
```

---

## 7. 安装 Python 依赖

> **⚠️ 版本锁定（2026-05-18 烟测后更新）**
>
> 本节早期版本写的是 torch 2.4.0+cu121 / transformers 4.45 / trl 0.16，在 2026-05-18 烟测时遇到三处报错：
> 1. `torch._library.infer_schema` 不识别字符串形式注解 → 必须升 torch ≥ 2.5。
> 2. SwanLab init 时 `cfg["sft"]["max_seq_length"]` KeyError → 已在脚本中加兼容回退。
> 3. trl 0.16+ `assistant_only_loss` 模板不通过 → 已在 train_qlora.py 引入训练专用简化模板。
>
> 推荐用根目录下的 [`requirements-server-finetuning.txt`](../../requirements-server-finetuning.txt) 一次性安装：
>
> ```bash
> conda activate ickg
> pip install --upgrade pip
> pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
>     --index-url https://download.pytorch.org/whl/cu124
> pip install -r requirements-server-finetuning.txt
> ```
>
> 下面 7.1–7.7 的命令保留了首次踩坑时的原始记录，**新环境请优先用上面的 requirements 文件**。

```bash
# 7.1 配置 pip 国内镜像
mkdir -p ~/.pip
cat > ~/.pip/pip.conf <<'EOF'
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
extra-index-url = https://download.pytorch.org/whl/cu124
EOF

# 7.2 升级 pip
pip install --upgrade pip

# 7.3 安装 PyTorch 2.6.0 + CUDA 12.4（与驱动 CUDA 12.4 对齐，A100 SM80 完美兼容）
pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
    --index-url https://download.pytorch.org/whl/cu124

# 7.4 验证 torch + CUDA
python -c "import torch; print('torch:', torch.__version__, 'cuda:', torch.cuda.is_available(), 'device:', torch.cuda.get_device_name(0))"
# 应输出：torch: 2.6.0+cu124  cuda: True  device: NVIDIA A100-SXM4-80GB
```

> **关于 CUDA 版本对齐（2026-05-28 现状）**
>
> 当前驱动 CUDA Version 12.4 / torch wheel cu124 / flash-attn 在 torch 2.6 + cu124 下重装通过。三者全部对齐到 12.4，不再需要前向兼容兜底。
>
> 1. **`nvidia-smi` 显示的 CUDA Version 是驱动支持的最高 CUDA Toolkit 版本**（12.4），torch cu124 wheel 内置 12.4 运行时，无冲突。
> 2. **A100 (SM80)** 在 cu124 wheel 上一阶 / 二阶算子均完整支持。
> 3. **flash-attn 2.6.3** 已在本环境（torch 2.6 / cu124 / cxx11abi=False / py3.10）下 import 通过；如换 torch / cuda 大版本需要重新编译或换 wheel。
>
> 历史背景（旧手册中的 torch 2.4 + cu121 + flash-attn cu123 三件套，已在 2026-05-18 烟测时被 §7 顶部的 ⚠️ 列出的三处报错驱动升级到当前版本）。
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
# 7.5 安装核心训练栈（推荐：直接用 requirements-server-finetuning.txt，对应版本已在 2026-05-18 烟测验证）
pip install -r requirements-server-finetuning.txt

# 或者手动装（与 requirements 文件等价）：
# pip install \
#   "transformers==5.8.1" \
#   "peft==0.19.1" \
#   "trl==1.4.0" \
#   "accelerate==1.13.0" \
#   "bitsandbytes==0.49.2" \
#   "datasets>=4.0" \
#   "swanlab>=0.7.0" \
#   "tensorboard>=2.17.0" \
#   "pyyaml>=6.0" \
#   "scipy>=1.13.0" \
#   "sentencepiece>=0.2.0"

# 7.6 验证关键依赖一并打印
python -c "import torch, transformers, peft, accelerate, bitsandbytes, trl; \
  print('torch:', torch.__version__, 'cuda:', torch.cuda.is_available()); \
  print('transformers:', transformers.__version__); \
  print('peft:', peft.__version__); \
  print('accelerate:', accelerate.__version__); \
  print('bitsandbytes:', bitsandbytes.__version__); \
  print('trl:', trl.__version__)"
# 期望输出（2026-05-28 实测）：
#   torch: 2.6.0+cu124  cuda: True
#   transformers: 5.8.1
#   peft: 0.19.1
#   accelerate: 1.13.0
#   bitsandbytes: 0.49.2
#   trl: 1.4.0

python -m bitsandbytes
# 应看到 "PyTorch installed: True" 和 "Library not detected: False"
```

### 7.7 安装 Flash Attention 2（可选但强烈推荐）

A100 + 长序列开启 FA2 可省 ~30% 显存、加速 1.5-2x。当前环境实测 flash-attn 2.6.3 与 torch 2.6.0+cu124 兼容。

```bash
# 7.7.1 优先尝试 pip 直装（若仓库缓存了 torch 2.6 / cu124 的 wheel 则秒装；否则会源码编译，~10-20 min）
pip install flash-attn==2.6.3 --no-build-isolation

# 7.7.2 若编译超时，去 https://github.com/Dao-AILab/flash-attention/releases
#       找对应 wheel：cp310 / linux_x86_64 / cxx11abiFALSE / 与本机 torch + cuda 大版本匹配
#       例如可尝试（请按 release 页面实际命名替换）：
# pip install https://github.com/Dao-AILab/flash-attention/releases/download/v2.6.3/flash_attn-2.6.3+cu124torch2.6cxx11abiFALSE-cp310-cp310-linux_x86_64.whl

# 7.7.3 验证（不只是 import 通过，还要确认 fwd kernel 可调用）
python -c "import torch, flash_attn; \
  from flash_attn import flash_attn_func; \
  x = torch.randn(2, 4, 8, 16, dtype=torch.bfloat16, device='cuda'); \
  print('flash-attn:', flash_attn.__version__, 'fwd OK, output shape:', flash_attn_func(x, x, x).shape)"
# 预期：flash-attn: 2.6.3 fwd OK, output shape: torch.Size([2, 4, 8, 16])
```

**如果 FA2 装不上**：编辑 `src/Fine_tuning/configs/train_config.yaml`，把 `attn_implementation: "flash_attention_2"` 改为 `attn_implementation: null`，模型走默认 SDPA / eager 注意力，性能略降但能跑（显存峰值会增加 ~10 GB，bsz 可能需要调小）。

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

烟测通过后启动正式训练。**强烈建议用 `tmux` 防止 SSH 断开 / 网络抖动导致训练中止**——14 小时的训练任何中断都会前功尽弃。

> **服务器现状（2026-05-28 实测）**：tmux 3.2a 已预装在 `/usr/bin/tmux`，无需另装。

#### 11.1 tmux 使用速查（按出现频率排序）

```bash
# (a) 新建会话——名字叫 train（之后所有引用都用这个名字）
tmux new -s train

# (b) 列出当前所有会话
tmux ls

# (c) 重新连接到指定会话（SSH 断了之后回来必用）
tmux attach -t train

# (d) 临时离开会话（训练继续）：在 tmux 内按 Ctrl+B，松开后再按 D
#     此时回到外层 shell，但 tmux 里的训练进程仍在跑

# (e) 彻底关闭会话（训练已结束 / 想强杀）
tmux kill-session -t train
```

**tmux 内部快捷键**（前缀都是 `Ctrl+B`，先按下放开，再按下面的键）：

| 操作 | 快捷键 | 说明 |
|---|---|---|
| Detach（离开但保留会话） | `Ctrl+B` `D` | 训练继续在后台跑，SSH 可以安全断开 |
| 滚屏 / 复制模式 | `Ctrl+B` `[` | 进入后用方向键 / `PgUp` `PgDn` 看历史；按 `q` 退出 |
| 横向分屏 | `Ctrl+B` `"` | 上下分两个 pane（例如上 pane 跑训练、下 pane 跑 `nvidia-smi`） |
| 纵向分屏 | `Ctrl+B` `%` | 左右分两个 pane |
| 在 pane 之间切换 | `Ctrl+B` `方向键` | 在分出的 pane 之间跳 |
| 关闭当前 pane | `Ctrl+B` `x` | 然后按 `y` 确认 |
| 新建窗口 | `Ctrl+B` `c` | 一个会话里可有多个 window |
| 切换窗口 | `Ctrl+B` `n` / `p` | next / prev |
| 列出窗口 | `Ctrl+B` `w` | 用方向键选 |
| 重命名窗口 | `Ctrl+B` `,` | 输入新名字 |

> **可选：启用鼠标滚轮**（一次性设置，之后所有会话都生效）
>
> ```bash
> cat > ~/.tmux.conf <<'EOF'
> set -g mouse on
> set -g history-limit 50000
> EOF
> tmux source-file ~/.tmux.conf   # 已在会话内时执行；新会话自动生效
> ```

#### 11.2 启动训练（tmux 内）

```bash
# (1) 在本地终端先连服务器
ssh 医学集群

# (2) 新建 tmux 会话
tmux new -s train

# (3) 在会话内启动训练（一行命令做 4 件事：cd → activate env → 启动训练 → 同时 tee 到带时间戳的日志）
cd /root/ICKG && conda activate ickg && \
  mkdir -p log/Fine_tuning && \
  python src/Fine_tuning/training/train_qlora.py \
    --config src/Fine_tuning/configs/train_config.yaml \
    2>&1 | tee log/Fine_tuning/train_$(date +%Y%m%d_%H%M%S).log

# (4) 按 Ctrl+B D 离开会话（训练继续），可以安全断开 SSH
#     回来时：ssh 医学集群 → tmux attach -t train

# (5) 训练中途想看 GPU，先 Ctrl+B " 横向分屏，下 pane 执行：
watch -n 2 nvidia-smi
```

#### 11.3 训练异常排查（在 tmux 外也能查）

```bash
# 看最新一条训练日志
ls -1t /root/ICKG/log/Fine_tuning/train_*.log | head -1 | xargs tail -100

# 看 tmux 里训练进程是否还活着（看 GPU 占用 + 进程号）
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv

# 万一 tmux 内训练崩了想看完整 stderr：
tmux attach -t train      # 重新进会话，往上滚 (Ctrl+B [) 看堆栈
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

### 13.4 推理 prompt 对齐校验（vLLM 部署前必跑）⭐

> 背景：本项目训练时启用了 `sft.assistant_only_loss: true`，trl 0.16+ 拒绝官方 Baichuan-M2 模板，所以训练期临时切换到了简化模板（去掉空 `<think>\n\n</think>\n\n` 壳）。保存时已还原成官方模板，但**只有在调用 `apply_chat_template` 时不传 `thinking_mode` 才能匹配训练分布**。详见 [error/smoke-test/烟测报错处理评估报告.md](../../error/smoke-test/烟测报错处理评估报告.md) §3。

```bash
# 13.4.1 校验 adapter 目录的 tokenizer 推理 prompt 末尾与训练分布对齐
python src/Fine_tuning/tools/verify_adapter_inference_alignment.py \
  --adapter-dir models/Baichuan-M2-32B-QLoRA-v1/adapter \
  --sample-jsonl data/Fine_tuning_dataset/training_ready/v1/val.jsonl \
  --strict-thinking-mode-check

# 期望输出：
# [OK] 默认调用 prompt 末尾为 "<|im_start|>assistant\n"，与训练分布对齐。
# [OK] 真实样本 prompt 末尾同样对齐（取自 val.jsonl）。
# [完成] adapter tokenizer 与训练分布在 prompt 边界处对齐校验通过。
```

**vLLM 部署硬规则**：

- ❌ 不要在 vLLM 启动参数或客户端调用里传 `chat_template_kwargs={"thinking_mode": ...}`。
- ❌ 不要传 `enable_thinking` 之外的任何 thinking 相关参数（`enable_thinking=False` 在 Baichuan-M2 模板里恰好是 no-op，安全）。
- ✅ 让 jinja 走默认分支，prompt 收尾就是 `<|im_start|>assistant\n`，与训练完全对齐。
- ✅ 如果业务方要求"明确禁用思考"，请在 system prompt 里用自然语言说明，**不要**通过模板参数注入。

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
# Pip mirror（与当前 torch wheel 对齐到 cu124）
mkdir -p ~/.pip && cat > ~/.pip/pip.conf <<EOL
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
extra-index-url = https://download.pytorch.org/whl/cu124
EOL
# Deps（与 2026-05-18 烟测验证版本一致）
pip install --upgrade pip
pip install torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
    --index-url https://download.pytorch.org/whl/cu124
cd /root/ICKG && pip install -r requirements-server-finetuning.txt
echo "[完成] 基础环境已就绪。后续执行 flash-attn 安装、swanlab login、模型下载、训练。"
EOF
chmod +x /root/setup_server.sh
```

> 该脚本依赖仓库根目录的 `requirements-server-finetuning.txt`，所以要 **先 `git clone` 完仓库**（§6）再跑此脚本，或者跑前先 `cd /root && git clone https://github.com/ThinkingUniverse/ICKG.git`。

---

完。


---

## 18. vLLM 推理部署与运维（Phase 10，2026-06）

> 本节补记**合并权重之后的大规模推理**全套操作。训练用 `ickg` 环境；**推理另起独立环境 `vllm_env`**（避免污染已锁版本的 ickg）。脚本均在 `scripts/vllm_inference/`。

### 18.1 环境：vllm_env（🔴 版本必须锁，否则跑不起来）
- **驱动 550.163.01 = CUDA 12.4 上限**。最新 vllm（0.22+）依赖 torch 2.11 + **CUDA 13**（cu13），需驱动 580+，**本机跑不起来**。
- 锁定：**`vllm==0.8.5.post1` + torch 2.6.0+cu124 + `transformers==4.51.3`**（vllm 0.8.5 会调 `Qwen2Tokenizer.all_special_tokens_extended`，transformers 5.x 删了它会崩；pip 默认装 5.x，需手动降到 4.51.3）。
```bash
source /root/miniconda3/etc/profile.d/conda.sh
conda create -n vllm_env python=3.12 -y          # conda 报 HTTP 000 时：conda config --set ssl_verify false
conda activate vllm_env
pip install vllm==0.8.5.post1                      # 见 18.6：pip 镜像建议改阿里云
pip install transformers==4.51.3                   # 降级，必须
```

### 18.2 起服务（02_serve_vllm.sh，放 tmux）
```bash
tmux new -s vllm_serve -d 'source /root/miniconda3/etc/profile.d/conda.sh && conda activate vllm_env && cd ~/ICKG && \
  MAX_MODEL_LEN=12288 GPU_MEM_UTIL=0.95 EXTRA_ARGS="--tokenizer models/hf/Baichuan-M2-32B" \
  bash scripts/vllm_inference/02_serve_vllm.sh 2>&1 | tee log/vllm_serve.log'
# 就绪判断：curl -s http://127.0.0.1:8801/v1/models
```
🔴 **必须 `--tokenizer models/hf/Baichuan-M2-32B`（base 词表）**：merged 目录只有 tokenizer.json、**缺 vocab.json/merges.txt**，vLLM 会回退慢速 `Qwen2Tokenizer` 并崩（`AttributeError: Qwen2Tokenizer has no attribute all_special_tokens_extended`）。base 目录词表齐全（同一词表）。
- 服务参数：`--max-model-len 12288 --gpu-memory-utilization 0.95 --enable-prefix-caching --disable-log-requests`，**绝不加任何 reasoning/thinking 开关**（对齐铁律）。
- 实测 KV cache 仅 ~48k token、12288 并发上限 3.98x → 并发是吞吐关键。

### 18.3 数据准备（本地）+ 上传分片
```bash
# 本地（ickg python）：剔除已提取、切 20 片
python scripts/vllm_inference/01_filter_split.py --num-shards 20
# 压缩上传到远端同路径
tar -czf input_shards.tar.gz input_shards && scp input_shards.tar.gz 医学集群:/root/ICKG/data/vllm_inference/
ssh 医学集群 "cd ~/ICKG/data/vllm_inference && tar -xzf input_shards.tar.gz"
```

### 18.4 跑全量（监工自愈，强烈推荐）
```bash
# 监工：客户端卡死/退出自动重启续跑，done_pmids.txt 断点续跑
tmux new -s vllm_extract -d 'source /root/miniconda3/etc/profile.d/conda.sh && conda activate vllm_env && \
  bash scripts/vllm_inference/run_extract_supervised.sh'
# 监工内部即 03_extract_client.py --concurrency 32 --temperature 0 --max-tokens 2560
```
🔴 **必须用监工**：客户端曾因 writer 协程静默死锁**卡死 3.5 天、GPU 空转白烧 ~580 元**才被发现。监工每 STALL 秒（默认300）检测日志不增长即判卡死、杀掉重启。

### 18.5 截断补尾（主推理跑完后，可选；ROI 低需评估）
```bash
# 编排：等主推理结束→自动接 06 全部补尾→合并 triples_merged.jsonl
tmux new -s vllm_recover -d 'source /root/miniconda3/etc/profile.d/conda.sh && conda activate vllm_env && \
  bash scripts/vllm_inference/run_recover_after_main.sh'
# 中断：tmux kill-session -t vllm_recover; pkill -f 06_recover_truncated
# 只合并不补尾（定稿）：bash 一个含 `python 06_recover_truncated.py --merge-only` 的小 .sh
```
⚠️ 补尾实测仅 0.04 篇/s、净增 +0.3 条/篇，全部补尾 ~20 天/~3,362 元、ROI 极差。**截断篇经"残片打捞"后已有中位 14 条三元组（高于正常篇），一般可不补尾**，直接 `06 --merge-only` 定稿即可。

### 18.6 运维踩坑速查（本阶段实战）
| 现象 | 原因 / 解决 |
|---|---|
| 装 vllm 自动拉 cu13/torch2.11 | 驱动只到 CUDA12.4，**锁 vllm==0.8.5.post1**（配 cu124 torch） |
| vLLM 起服务崩 `all_special_tokens_extended` | merged 缺 vocab.json/merges.txt → serve 加 `--tokenizer models/hf/Baichuan-M2-32B` |
| 约 10–24% 文章截断/复读、吞吐崩 | 贪心+高并发批次非确定性复读；客户端已加**残片打捞+去重**根治，并 max_tokens=2560 |
| 客户端 GPU 0% 但进程在、日志停 | writer 协程静默死锁 → **监工 run_extract_supervised.sh** 自愈 |
| conda 报 HTTP 000 | `conda config --set ssl_verify false` |
| pip 清华源大 wheel 超时 | pip.conf 改阿里云：`index-url=https://mirrors.aliyun.com/pypi/simple/` |
| SSH 频繁 `Connection closed/timed out 255` | 国内链路抖动/大下载占带宽；加 `-o ServerAliveInterval=15`，命令拆短、失败即重连 |
| 远端→HF 大文件/建仓超时 | `pip install hf_transfer` + `HF_HUB_ENABLE_HF_TRANSFER=1` + 重试循环；建仓单独重试 |
| 本地钩子拦裸 `python` | `.claude/hooks/enforce_ickg_env.py` 拦含 `python` 的本地命令；远端跑 python 改写 .sh 再 `bash`，或用 cat/scp/hf/curl/wc 绕开 |

### 18.7 HuggingFace 发布（公开数据集 + adapter）
```bash
conda activate vllm_env   # 有 hf 0.36 CLI + hf_transfer
export HF_TOKEN=hf_xxx HF_HUB_ENABLE_HF_TRANSFER=1
hf upload Siyu2Zhou/ICKG-immunology-triple-extraction-sft <local> <path_in_repo> --repo-type dataset
hf upload Siyu2Zhou/Baichuan-M2-32B-QLoRA-immunology-triples models/.../adapter . --repo-type model
```
- adapter 仓库须含**完整 tokenizer**（从 base 拷 vocab.json/merges.txt/added_tokens.json/special_tokens_map.json）+ chat_template.jinja + 提示词，否则用户复现会撞 18.6 的 tokenizer 报错。
- 🔴 token 用完即去 HF Settings 轮换（明文出现过即视为泄露）。

### 18.8 监控与收尾
```bash
# 进度/健康（用 ! 直接跑）
ssh 医学集群 "wc -l ~/ICKG/data/vllm_inference/output/_state/done_pmids.txt; tail -3 ~/ICKG/log/vllm_extract.log"
# 全部完成后：停服务释放 GPU → 控制台「停机」止损（停机保留磁盘，释放才删数据）
ssh 医学集群 "tmux kill-session -t vllm_serve"
```
最终产物 `data/vllm_inference/output/triples_merged.jsonl`（786 万三元组）→ 下游实体对齐 `scripts/Entity_alignment`。
