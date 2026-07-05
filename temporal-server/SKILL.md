---
name: temporal-server
description: Temporal 开发服务器运维。启动/停止/状态检查/外网访问配置/防火墙/代理排障。当用户提到 temporal server、temporal dev、temporal 启动、temporal 连不上、temporal 外网访问、temporal start-dev、Temporal UI、Temporal 端口、7233、8233 时触发。即使用户只说"帮我把 temporal 开一下"或"temporal 好像挂了"也应该触发。
---

# Temporal Server 运维

Temporal 开发服务器的日常管理：启动、停止、状态检查、外网暴露、故障排查。

> 当前服务器配置：[server-config](references/server-config.md)

---

## 命令速查

| 操作 | 命令 |
|------|------|
| 启动（仅本地） | `temporal server start-dev` |
| 启动（监听所有网卡） | `temporal server start-dev --ip 0.0.0.0 --ui-port 8233` |
| 启动（持久化） | `添加 --db-filename /path/to/store.db` |
| 后台启动 | `nohup ... > /tmp/temporal-dev.log 2>&1 &` |
| 停止 | `pkill -f "temporal server start-dev"` |
| 状态检查 | `ss -tlnp \| grep -E '7233\|8233'` |
| 进程检查 | `ps aux \| grep "temporal server" \| grep -v grep` |

---

## 启动

### 基本启动（仅本地访问）

```bash
temporal server start-dev
```

默认：gRPC `localhost:7233`，Web UI `localhost:8233`。

### 允许外网 / 内网其他机器访问

绑定到所有网卡：

```bash
temporal server start-dev --ip 0.0.0.0 --ui-port 8233
```

⚠️ Dev Server 没有认证机制，直接暴露到公网有安全风险。建议配合防火墙白名单或 frp/VPN 使用。

### 后台运行

`start-dev` 是前台进程，关闭终端会退出。后台运行：

```bash
nohup temporal server start-dev --ip 0.0.0.0 --ui-port 8233 > /tmp/temporal-dev.log 2>&1 &
```

### 持久化 Workflow 数据

默认重启后所有数据丢失。加 `--db-filename` 持久化：

```bash
temporal server start-dev --db-filename /home/ubuntu/temporal-store.db
```

### 启动失败排查

常见原因及解决：

| 症状 | 原因 | 解决 |
|------|------|------|
| `context deadline exceeded` | 代理环境变量干扰 | 启动前 `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY` |
| `bind: address already in use` | 端口被占用 | `pkill -f "temporal server"` 后重试，或换端口 `--port 7234 --ui-port 8234` |
| 日志为空 | stdout 被缓冲 | 加 `2>&1` 重定向 stderr，或直接在前台启动查看输出 |

---

## 停止

```bash
# 优雅停止
pkill -f "temporal server start-dev"

# 确认已停止
ss -tlnp | grep -E '7233|8233'
```

---

## 状态检查

```bash
# 端口是否在监听（*:7233 和 *:8233 表示正常）
ss -tlnp | grep -E '7233|8233'

# 进程是否存在
ps aux | grep "temporal server" | grep -v grep

# Web UI 是否响应（注意：有代理时需绕过）
curl -s --noproxy '*' -o /dev/null -w "%{http_code}" http://localhost:8233/
# 返回 200 即正常
```

---

## 外网访问

### 1. 绑定网卡

启动时必须加 `--ip 0.0.0.0`，否则只监听 localhost。

### 2. 防火墙放行

检查并放行端口（本机使用 ufw）：

```bash
# 查看当前规则
sudo ufw status | grep -E '7233|8233'

# 放行
sudo ufw allow 7233/tcp
sudo ufw allow 8233/tcp
```

### 3. 云安全组

如果服务器在腾讯云/AWS 等云上，还需要在云控制台的安全组中放行 TCP 7233 和 8233。

### 4. 代理干扰

如果本机配置了 `http_proxy`（如 `http://127.0.0.1:7892`），访问本地端口时会被代理转发导致 502。解决：

```bash
# 访问本地时绕过代理
curl --noproxy '*' http://localhost:8233/

# 或临时清除代理
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
```

### 安全建议

- 尽量用 **frp 内网穿透**（`frp-tunnel-setup` skill）而非直接暴露端口
- 或用 **WireGuard 组网**（`wireguard-setup` skill）将客户机纳入内网
- 必须公网暴露时，用 nginx 反向代理 + TLS + 基础认证

---

## 常用参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--ip` | 绑定 IP | `127.0.0.1` |
| `--port` | gRPC 端口 | `7233` |
| `--ui-port` | Web UI 端口 | `gRPC端口 + 1000` |
| `--http-port` | HTTP API 端口 | 随机 |
| `--db-filename` | 持久化存储路径 | 无（内存模式） |
| `--headless` | 禁用 Web UI | false |
| `--dynamic-config-value` | 动态配置 KEY=VALUE | - |
