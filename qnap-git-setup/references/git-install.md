# 在 QNAP NAS 上安装 git

## 前置条件

QNAP NAS 运行 QTS 系统（基于定制 Linux），没有 `apt` / `yum` 等常规包管理器。

git 通过 **Entware**（QNAP 的 opkg 包管理）安装。

## 确认 Entware 已安装

```bash
ls /opt/bin/opkg
```

如果不存在，需先在 QNAP App Center 中安装 "Entware-std" 应用。

## 安装步骤

### 方法 A：以 admin 身份 SSH 安装（推荐）

当前用户（如 `slb1988`）没有 `/opt/` 写权限（目录属于 `admin:administrators`），opkg 会静默安装失败（安装过程中 Permission denied，但不报致命错误退出码）。

**正确做法**：以 admin 用户 SSH 到 NAS，执行：

```bash
/opt/bin/opkg update
/opt/bin/opkg install git git-http
```

安装完成后验证：

```bash
/opt/bin/git --version
# git version 2.50.1
```

### 方法 B：通过 sudo 安装

```bash
sudo /opt/bin/opkg update
sudo /opt/bin/opkg install git git-http
```

如果 sudo 不可用（非管理员用户），仍需切到 admin 使用。

## 验证 git 可用

```bash
/opt/bin/git --version
```

## 设置 PATH 全局生效

将 `/opt/bin` 加入 PATH，写入 `~/.profile`：

```bash
echo 'export PATH="/opt/bin:$PATH"' >> ~/.profile
```

确保 `/opt/bin` 在 PATH 最前面（覆盖系统可能存在的旧版本）：

```bash
# ~/.profile 中确保如下内容：
export PATH="/opt/bin:$HOME/.local/npm/bin:$HOME/.local/bin:$HOME/.local/opt/node/bin:$PATH"
```

之后每次登录自动生效。当前 session 手动 export：

```bash
export PATH="/opt/bin:$PATH"
```

## 常见问题

### opkg 安装时 Permission denied

```
* wfopen: //opt/lib/opkg/info/zlib.control: Permission denied.
* pkg_write_filelist: Failed to open ...: Permission denied.
* opkg_install_cmd: Cannot install package git.
```

**原因**：当前用户没有 `/opt/` 目录的写权限（owner 是 `admin`）。

**解决**：以 admin 身份 SSH 登录再执行 opkg 安装。

### git 命令识别不到

已安装但 `which git` 无输出，检查：

```bash
/opt/bin/git --version  # 确认二进制存在
echo $PATH              # 确认 /opt/bin 在 PATH 中
```

### 包列表更新失败

```
Downloading http://bin.entware.net/x64-k3.2/Packages.gz
*** Failed to download the package list from http://bin.entware.net/x64-k3.2/Packages.gz
```

**原因**：Entware 仓库网络不通（可能被墙或 DNS 问题）。

**解决**：配置代理后重试，或更换镜像源。
