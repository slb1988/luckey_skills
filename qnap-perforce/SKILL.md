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
| **P4PORT** | `192.168.50.2:1666` |
| **ServerID** | `NAS453Dmini` |
| **二进制路径** | `/usr/local/bin/p4` `/usr/local/bin/p4d` `/usr/local/bin/p4broker` `/usr/local/bin/p4p` |
| **License** | slb1988, 100 users, 10年 (至 2036/07/04) |
| **启动方式** | 手动守护进程: `p4d -r /share/Container/p4server -p 192.168.50.2:1666 -d` |

**当前配置 (`p4 configure show allservers`)**:
```
P4PORT = 192.168.50.2:1666
dm.user.noautocreate = 2
monitor = 1
```

### 旧环境（Docker，待下线）

Docker 版 Perforce 容器 `helix-p4d-1`，数据在 `/share/Container/perforce`。详见：
- 容器配置 & OOM 排障 → `references/docker-p4d.md`
- 完整数据库清单、历史事件 → `references/p4d-server.md`
- 通用诊断/护栏运维 → `references/p4-diagnostics-ops.md`

## 本地连接

```bash
export P4PORT=192.168.50.2:1666
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

```bash
# 启动
p4d -r /share/Container/p4server -p 192.168.50.2:1666 -d

# 停止
p4 -p 192.168.50.2:1666 admin stop
# 或直接 kill
kill $(ps aux | grep 'p4d.*p4server' | grep -v grep | awk '{print $2}')
```

## Checkpoint / 备份

```bash
# 手动 checkpoint
p4d -r /share/Container/p4server -jc

# 恢复 checkpoint
p4d -r /share/Container/p4server -jr <checkpoint_file>
p4d -r /share/Container/p4server -xu  # 升级数据库（如跨版本恢复）
```

## 迁移状态

**待完成**（需手动操作，depot 文件 ~28GB 耗时较长）：
```bash
# 1. 拷贝旧 depot archive 文件
cp -a /share/Container/perforce/{depot,unity,ProjectB,ProjectC,DevOps,Plugins} /share/Container/p4server/

# 2. 清理并恢复 checkpoint
rm -rf /share/Container/p4server/db.* /share/Container/p4server/journal /share/Container/p4server/server.locks
p4d -r /share/Container/p4server -jr /share/Container/perforce_backup/p4_backup.ckp.9

# 3. 启动
p4d -r /share/Container/p4server -p 192.168.50.2:1666 -d
```

Checkpoint 已就绪: `/share/Container/perforce_backup/p4_backup.ckp.9` (467MB, 已验证)
