---
name: qnap-perforce
description: QNAP NAS 上的 Perforce (Helix Core) 服务器运维。当用户提到 QNAP Perforce、p4d、helix-p4d、P4 服务器、Perforce 迁移、checkpoint、P4 备份、NAS version control、P4 depot 维护、p4d 原生部署、Docker Perforce 故障时触发。即使用户只是抱怨 "P4 连不上了" 或 "perforce server down"，也应触发。
---

# QNAP Perforce 运维

## 环境概览

| 项目 | 值 |
|---|---|
| **NAS 型号** | QNAP NAS453Dmini |
| **CPU** | Intel Celeron J4125 (4核, x86_64) |
| **内存** | 8GB DDR4 |
| **主机名** | NAS453Dmini |

### 当前环境（原生 p4d）

迁移至原生方案，不再依赖 Docker。

| 项目 | 值 |
|---|---|
| **p4d 版本** | P4D/LINUX26X86_64/2024.1/2596294 (2024/05/09) |
| **P4ROOT** | `/share/Container/p4server` |
| **P4PORT** | `1666` |
| **ServerID** | `NAS453Dmini` |
| **二进制路径** | `/usr/local/bin/p4` `/usr/local/bin/p4d` `/usr/local/bin/p4broker` `/usr/local/bin/p4p` |
| **License** | slb1988, 100 users, 10年 (至 2036/07/04) |
| **启动方式** | 开机自启: `@reboot` 在系统 crontab (`/etc/config/crontab`) |

**当前配置 (`p4 configure show allservers`)**:
```
P4PORT = 1666
dm.user.noautocreate = 2
monitor = 1
unicode = 1
journalPrefix = /share/Container/p4server/checkpoints/NAS453Dmini
```

**Server 类型**: `commit-server`

### 旧环境（Docker，待下线）

Docker 版 Perforce 容器 `helix-p4d-1`，数据在 `/share/Container/perforce`。详见：
- 容器配置 & OOM 排障 → `references/docker-p4d.md`
- 完整数据库清单、历史事件 → `references/p4d-server.md`
- 通用诊断/护栏运维 → `references/p4-diagnostics-ops.md`
- Docker → 原生迁移实录 → `references/native-migration.md`

## 本地连接

```bash
export P4PORT=1666
p4 info
```

## 副本工具

| 工具 | 路径 | 用途 |
|---|---|---|
| `p4` | `/usr/local/bin/p4` | CLI 客户端 |
| `p4d` | `/usr/local/bin/p4d` | 服务端守护进程 |
| `p4broker` | `/usr/local/bin/p4broker` | Broker 代理（未部署） |
| `p4p` | `/usr/local/bin/p4p` | Proxy 代理（未部署） |
| Keygen | `/share/Container/r24.1.bin.linuxx64.helix-core-server/Keygen` | License 生成 |

## 启停

p4d 配置为系统开机自启，通过 `/etc/config/crontab` 的 `@reboot` 条目（延迟 30s 等待依赖就绪）。

```bash
# 手动启动
p4d -r /share/Container/p4server -p 1666 -L /share/Container/p4server/logs/log -J /share/Container/p4server/logs/journal -d

# 停止
p4 -p 1666 admin stop
# 或直接 kill
kill $(ps aux | grep 'p4d.*p4server' | grep -v grep | awk '{print $2}')
```

## 日志与 Journal

| 路径 | 用途 |
|---|---|
| `/share/Container/p4server/logs/log` | p4d 运行日志 (`-L`) |
| `/share/Container/p4server/logs/journal` | p4d journal (`-J`) |
| `/share/Container/p4server/checkpoints/NAS453Dmini` | checkpoint 前缀 (`journalPrefix`) |

## Checkpoint / 备份

```bash
# 手动 checkpoint
p4d -r /share/Container/p4server -jc

# 恢复 checkpoint
p4d -r /share/Container/p4server -jr <checkpoint_file>
p4d -r /share/Container/p4server -xu  # 升级数据库（如跨版本恢复）
```

## 迁移状态

✅ **已完成**（2026-07-05）。详细过程见 `references/native-migration.md`。

361,465 files / 7 depots，数据与 Docker 版一致。
