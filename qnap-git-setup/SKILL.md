---
name: qnap-git-setup
description: QNAP NAS 运维工具，支持：(1) 配置 git、生成 SSH key 并绑定 GitHub，(2) 固件更新——型号/平台识别与正确固件包选择。当用户提到"QNAP 装 git"、"NAS git"、"NAS 连接 GitHub"、"NAS SSH key"、"QNAP GitHub"、"NAS 上拉代码"、"NAS git clone 报错"时触发 git 功能；提到"QNAP 升级"、"固件更新"、"QTS 升级失败"、"手动更新固件"、"错误码 6"、"错误码 32"、"固件包解压错误"时触发固件功能。即使用户只抱怨"QNAP 上找不到 git"或"固件更新报错"也应该考虑使用此 Skill。
---

# QNAP NAS 运维

## 平台识别

QNAP 型号命名区分产品线，**有无后缀字母决定硬件平台**。

| 系列 | 平台 | CPU | 示例型号 | 固件目录 |
|---|---|---|---|---|
| TS-X53 | 旧款 x86 | 老 Celeron | TS-453A, TS-653A | `TS-X53` |
| TS-X53D | Gemini Lake | 新 Celeron | **TS-453Dmini**, TS-653D | `TS-X53D` |
| TS-X53B | Braswell | Celeron | TS-453B, TS-653B | `TS-X53B` |

**差一个 "D" 就是完全不同的产品线。** TS-X53 的固件不能用于 TS-X53D，反之亦然（错误码 32：硬件型号不符）。

### 型号查询命令

```bash
/sbin/getsysinfo model          # 显示型号名，如 TS-453Dmini
cat /etc/platform.conf          # 平台代号，如 X86_GEMINILAKE
getcfg System "Model" -f /etc/default_config/uLinux.conf          # 系列名，如 TS-X53D
```

### 固件下载 URL 模式

```
https://download.qnap.com/Storage/{系列}/{系列}_{日期}-{版本}.zip

示例（正确，TS-453Dmini 用）:
https://download.qnap.com/Storage/TS-X53D/TS-X53D_20260514-5.2.9.3499.zip

示例（错误，TS-453Dmini 不可用）:
https://download.qnap.com/Storage/TS-X53/TS-X53_20260514-5.2.9.3499.zip
```

## Git 与 GitHub SSH 连接配置

在 QNAP NAS 上通过 Entware 安装 git，生成 SSH key，绑定 GitHub 远程仓库。

QNAP 是定制 Linux（QTS），没有自带包管理器，git 需通过 Entware（opkg）安装。

详细操作步骤见以下文档：

- **安装 git** → [references/git-install.md](references/git-install.md) — opkg 安装、权限处理、PATH 配置
- **SSH Key 生成与 GitHub 绑定** → [references/ssh-github.md](references/ssh-github.md) — Ed25519 key 生成、添加 known_hosts、测试连接
- **绑定到已有仓库** → [references/bind-repo.md](references/bind-repo.md) — remote 设置、拉取推送验证
- **NAS 提交/更新（GitHub）** → [references/nas-commit.md](references/nas-commit.md) — 全局身份缺失、SSH vs HTTPS、提交身份与敏感值存放约定

## 快速参考

```bash
# 1. 安装 git（需 admin 或 sudo）
/opt/bin/opkg update && /opt/bin/opkg install git git-http

# 2. 设置 PATH 全局生效
echo 'export PATH="/opt/bin:$PATH"' >> ~/.profile

# 3. 生成 SSH key
ssh-keygen -t ed25519 -C "your-label@nas" -f ~/.ssh/id_ed25519 -N ""

# 4. 信任 GitHub 主机
ssh -o StrictHostKeyChecking=accept-new -T git@github.com

# 5. 设置 remote
cd /path/to/your/repo
git remote set-url origin git@github.com:USER/REPO.git

# 6. 开 SSH agent + ssh-add (重要)
eval $(ssh-agent -s) && ssh-add ~/.ssh/id_ed25519

# 5.6后如果遇到 sign_and_send_pubkey 问题，更新 known_hosts
# ssh-keygen -R github.com && ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts

# 7. 测试拉取
git fetch origin
```

> **⚠️ 关键**：opkg 安装时可能遇到 Permission denied（不报错但实际未安装），需以 admin 用户身份执行或使用 `sudo`。见 [references/git-install.md](references/git-install.md)。

> **⚠️ SSH Agent 必须启动**：QNAP 环境可能没有 ssh-agent，导致 git fetch 时出现 `sign_and_send_pubkey: no mutual signature algorithm` 错误。**每次重新登录或操作 git 远程仓库前**，务必执行：
> ```bash
> eval $(ssh-agent -s) && ssh-add ~/.ssh/id_ed25519
> ```
> 或写入 `~/.profile` 实现自动启动。
