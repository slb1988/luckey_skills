---
name: zen-server
description: Zen Storage Server (UE DDC) 运维：启停、缓存清理、GC、端口、日志。涉及 zen/zenserver/DDC/缓存/端口 时触发。即使用户只说"zen 怎么了"也应触发。
---

# Zen Storage Server

Unreal Zen Storage Server (团队共享 DDC)，提供 UE 项目的派生数据缓存服务。

## 关键路径

| 项目 | 路径 |
|---|---|
| 二进制目录 | `/opt/zen/` |
| zenserver 可执行文件 | `/opt/zen/zenserver` |
| zen 管理工具 | `/opt/zen/zen` |
| 数据目录 | `/data/zen/` |
| 日志文件 | `/data/zen/logs/zenserver.log` |
| systemd 服务文件 | `/etc/systemd/system/zenserver.service` |
| 新版本来源 | `~/zen`、`~/zenserver`（用户家目录） |

数据目录结构：
- `cache/` — DDC 缓存数据（namespace: `ue.ddc`、`ue4.ddc`）
- `cas/` — 内容寻址存储
- `gc/` — GC 元数据
- `logs/` — 运行日志
- `sessions/` — 客户端会话

## 服务管理

服务以 systemd 运行，用户为 `zen`。所有 systemctl 操作需要 `sudo`。

```bash
# 查看状态
systemctl status zenserver

# 重启
sudo systemctl restart zenserver

# 停止
sudo systemctl stop zenserver

# 启动
sudo systemctl start zenserver

# 查看日志
sudo journalctl -u zenserver -n 50 --no-pager
```

**当前运行参数**（来自 systemd service）：
```
/opt/zen/zenserver --port 8558 --data-dir /data/zen --http asio \
  --gc-cache-duration-seconds 1209600 --gc-interval-seconds 21600 \
  --gc-low-diskspace-threshold 21474836480 --cache-bucket-limit-overwrites --quiet
```

## 更新二进制

新版本二进制放在 `~/zen` 和 `~/zenserver`，更新流程：

```bash
sudo systemctl stop zenserver
sudo cp ~/zen ~/zenserver /opt/zen/
sudo chmod +x /opt/zen/zen /opt/zen/zenserver
sudo systemctl start zenserver
systemctl status zenserver --no-pager
```

> **注意**：直接 `cp` 到 `/opt/zen/` 会因"文本文件忙"失败，必须先 stop 服务。

## 端口

服务默认配置端口 8558，但可能被其他服务占用后自动重定向。查看实际端口：

```bash
# 方法1：查看 ps 进程
ps aux | grep zenserver | grep -v grep

# 方法2：zen 自带命令
/opt/zen/zen ps

# 方法3：查看日志
grep "relocated to base port" /data/zen/logs/zenserver.log
```

连接 zen 管理命令时使用 `-u http://localhost:<实际端口>`。如果自动重定位了，日志中会显示类似：
```
[inf] [server] Unreal Zen Storage Server - relocated to base port 8658
```

## 查看状态

```bash
/opt/zen/zen status --port <实际端口>

# 基本信息
/opt/zen/zen info --help  # 查看可用参数

# 运行进程
/opt/zen/zen ps
```

## 缓存管理

```bash
# 查看缓存概览（命名空间、大小、条目数）
/opt/zen/zen cache info -u http://localhost:<PORT>

# 查看缓存统计（命中率、读写量）
/opt/zen/zen cache stats -u http://localhost:<PORT>

# 查看某个 namespace 的详细内容（bucket 和 key）
/opt/zen/zen cache details -u http://localhost:<PORT> -n ue.ddc

# 强制清空整个 namespace 的缓存
/opt/zen/zen cache drop -u http://localhost:<PORT> -n ue.ddc
/opt/zen/zen cache drop -u http://localhost:<PORT> -n ue4.ddc

# 清空特定 bucket
/opt/zen/zen cache drop -u http://localhost:<PORT> -n ue.ddc -b <bucket名>
```

## GC（垃圾回收）

```bash
# 查看 GC 状态（计划、最近执行、释放空间）
/opt/zen/zen gc-status -u http://localhost:<PORT>

# 手动触发 GC（带 verbose 输出）
/opt/zen/zen gc -u http://localhost:<PORT> --verbose

# 强制清除过期缓存（设置 max cache duration 为 0 秒）
/opt/zen/zen gc -u http://localhost:<PORT> -m 0 --verbose

# 模拟运行（不实际删除）
/opt/zen/zen gc -u http://localhost:<PORT> -n --verbose

# 停止正在运行的 GC
/opt/zen/zen gc-stop -u http://localhost:<PORT>
```

**GC 关键参数说明**：
- `-m <seconds>`：最大缓存存活时间，默认 0（使用服务端配置），当前服务端配置为 1209600 秒（14天）
- `-d <bytes>`：磁盘使用软限制，达到后触发回收
- `-n`：dry run，跳过实际删除
- `-s`：同时回收小对象
- `--skipcid`：跳过 CAS 数据回收

## 查看实时日志

```bash
# 服务日志（运行日志 + GC 周期日志）
tail -f /data/zen/logs/zenserver.log

# 历史日志（滚动）
cat /data/zen/logs/zenserver.1.log
```

## Web UI

启动后在浏览器访问 `http://<服务器IP>:<实际端口>/dashboard/`。

## 常见操作速查

```bash
PORT=8658  # 替换为实际端口

# 快速健康检查
/opt/zen/zen ps
/opt/zen/zen gc-status -u http://localhost:$PORT

# 看缓存占了多少
/opt/zen/zen cache info -u http://localhost:$PORT

# 强力清缓存
/opt/zen/zen cache drop -u http://localhost:$PORT -n ue.ddc
/opt/zen/zen cache drop -u http://localhost:$PORT -n ue4.ddc

# 磁盘用量
du -sh /data/zen/
```
