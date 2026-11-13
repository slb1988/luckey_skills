---
name: flux-downloader
description: FluxDown（zerx-lab/FluxDown，Rust 多协议下载管理器）在 QNAP NAS 上的下载、校验、安装、升级与运维。当用户提到 FluxDown、fluxdown、装 FluxDown、FluxDown qpkg、FluxDown 升级、FluxDown 端口/打不开、17800 端口、fluxdownd、NAS 下载器换新，或要在 QNAP 上装/重装/升级这个下载器时触发。即使用户只说"FluxDown 装一下"、"FluxDown 打不开了"、"升级 FluxDown"也应触发。安装细节与踩坑记录在 references/install.md。
---

# FluxDown QNAP 运维

FluxDown 是 Rust 写的多协议下载管理器（HTTP/FTP/BT 磁力/HLS/DASH），上游仓库 https://github.com/zerx-lab/FluxDown 。本机（TS-453Dmini，x86_64）以 QPKG 形式部署 **FluxDown-Server**。

## 本机现状速查

| 项目 | 值 |
|------|-----|
| 安装路径 | `/share/CACHEDEV1_DATA/.qpkg/FluxDown/` |
| Web 端口 | `17800`（WebUI = `/`） |
| 访问地址 | http://192.168.50.2:17800/ （LAN）、http://10.77.77.6:17800/ （WireGuard） |
| 服务脚本 | `/share/CACHEDEV1_DATA/.qpkg/FluxDown/fluxdown.sh start\|stop\|restart` |
| 进程 | `fluxdown-agent --server` + `fluxdownd`（admin 用户） |
| 注册 | `/etc/config/qpkg.conf`（RC_Number 101，开机自启） |
| 安装包缓存 | `/share/Download/FluxDown-Server-<ver>-qnap-x64.qpkg` |

## 操作指引

- **安装 / 升级**：读 [references/install.md](references/install.md)。核心三步：GitHub releases 下 `qnap-x64.qpkg`（走本机 7890 代理 + Range 断点续传）→ 对 `SHA256SUMS-server.txt` 校验 → `sudo -S -u admin sh <pkg>` 安装。
- **状态检查**：`ps aux | grep -i flux`、`netstat -tln | grep 17800`、`getcfg -f /etc/config/qpkg.conf FluxDown Web_Port`。
- **排障**：先确认进程和 17800 监听；进程没了就 `fluxdown.sh restart`。Web UI 通但下载失败是应用层问题，去 Web 界面看任务日志。

## 安全约定

sudo/admin 密码**一律不写进任何文件**（skill、会话笔记、脚本都不例外）。需要提权时向用户要密码或请用户自行执行，命令模板里只留 `<admin密码>` 占位符。
