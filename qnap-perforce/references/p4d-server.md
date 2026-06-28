# Perforce Docker Server 完整参考

> 本文件记录 QNAP NAS (NAS453Dmini) 上 Docker Perforce 服务器的完整配置、历史和运维细节。
> 操作指南见 `../SKILL.md`。

## 目录

1. [环境信息](#环境信息)
2. [容器配置](#容器配置)
3. [数据库文件清单](#数据库文件清单)
4. [Depot 结构](#depot-结构)
5. [网络拓扑](#网络拓扑)
6. [备份系统](#备份系统)
7. [历史事件](#历史事件)
8. [健康检查日志样本](#健康检查日志样本)
9. [恢复流程](#恢复流程)

---

## 环境信息

| 项目 | 值 |
|---|---|
| **NAS 型号** | QNAP NAS453Dmini |
| **QTS 版本** | 5.2.9 |
| **CPU** | Intel x86_64 (Celeron J4125, 4核) |
| **内存** | 8GB DDR4 |
| **Docker 版本** | 27.1.2-qnap8 |
| **容器管理** | Container Station (QNAP GUI + CLI) |
| **数据存储** | `/share/CACHEDEV1_DATA` (RAID, 814GB) |
| **主机名** | NAS453Dmini |

## 容器配置

### 基本信息

```
容器名:     helix-p4d-1
镜像:       hawkmothstudio/helix-p4d:latest-data-4
映像 ID:    sha256:b0dad8427cede9... 
创建时间:   2024-10-19 22:03 (UTC+8)
平台:       linux/amd64
```

### 镜像说明

- 来源: https://github.com/hawkmoth-studio/perforce-docker
- 版本: 1.4.0 (2023-05-01 发布，已停更)
- 许可证: Apache-2.0
- 基础: Ubuntu
- p4d 版本: 2022.2 (P4D/LINUX26X86_64/2022.2/2407422, 2023/02/14)
- Swarm 版本: 2023.1 (未实际启用)

### 运行时配置

```yaml
# 等效 docker run 参数
--name helix-p4d-1
--restart always
--memory 4812963840    # 4.5GB
--memory-swap 9625927680  # 9.6GB (swap 5.1GB)
--cpus 4               # cpu-quota 400000
--ulimit nofile=65535:65535
-v /share/Container/perforce:/data/master/root:rw
-p 32768:1666           # P4PORT 端口映射
-p 32769:22             # SSH (未使用)
```

### 环境变量

```
P4NAME=admin
P4USER=p4admin
P4PASSWD=Sun1305329
P4PORT=1666
P4ROOT=/data/master/root
P4SSLDIR=/data/master/root/ssl
P4D_USE_UNICODE=true
HELIX_P4D_VERSION=2022.2
HELIX_SWARM_VERSION=2023.1
```

### Entrypoint 行为

`/docker-entrypoint.sh` 执行以下步骤：

1. 检查 `/data/master/root` 和 `/data/master/root/ssl` 权限
2. 切换到 Unicode 模式
3. 启动 local-only p4d 实例
4. 登录 local p4admin
5. 设置 `filetype.bypasslock=1`（Swarm 需要）
6. 设置 security level = 2
7. 停止 local-only p4d
8. 启动正式 p4d：`gosu perforce p4d -p 1666`

## 数据库文件清单

> 路径: `/share/Container/perforce/`，权限 uid=105(perforce) gid=106

### 核心数据表（越大越需要关注）

| 文件 | 大小 | 最后修改 | 说明 |
|---|---|---|---|
| `db.rev` | 162 MB | 2026-06-17 | 修订记录（最大） |
| `db.revhx` | 133 MB | 2026-06-17 | 修订头部索引 |
| `db.revcx` | 78 MB | 2026-06-17 | 修订跨引用 |
| `db.have` | 73 MB | 2026-06-17 | 客户端 have list |
| `db.working` | 36 MB | 2026-06-17 | 工作区状态 |
| `db.storage` | 66 MB | 2026-06-17 | 存储记录 |
| `db.integed` | 70 MB | 2025-12-13 | 集成记录 |
| `db.resolve` | 25 MB | 2025-12-13 | 解决记录 |
| `db.locks` | 17 MB | 2026-06-17 | 文件锁 |
| `db.revdx` | 11 MB | 2026-05-13 | 修订数据索引 |
| `checkpoint.1` | 378 MB | 2025-08-09 | **最后一次 checkpoint** |
| `journal.0` | 1.7 GB | 2025-08-09 | Journal 日志 |
| `journal` | 240 B | 2026-06-28 | 当前 journal |

### 元数据表（均 ≤ 16KB）

`db.domain`, `db.user`, `db.group`, `db.protect`, `db.config`, `db.counters`, `db.server`, `db.depot`, `db.view`, `db.stream`, `db.trigger`, `db.ticket`, `db.ldap`, `db.property`, `db.upgrades` 等。

### 锁目录

`server.locks/` — 28+ clients, 9 streams, 其他 meta lock 文件。这些是运行时文件，正常停止时会清理。

## Depot 结构

| Depot | 大小 | 说明 |
|---|---|---|
| `001-Common` | 3.0 GB | 公共工程（DevOps, TeamCity 等） |
| `200-Work` | **16 GB** | 最大 depot，UE 项目（RPG 等） |
| `300-Learning` | 262 MB | 学习项目（DLPytorch 等） |
| `100-Personal` | 2.4 MB | 个人项目 |
| `1-Work` | 40 KB | 工作项目 |

此外还有 `.claude`, `.GUI`, `.p4ignore,d` 等特殊目录（Perforce 的 graph depot 结构）。

## 网络拓扑

```
QNAP NAS (NAS453Dmini)
├── 物理网卡: 192.168.50.2 (局域网)
├── docker bridge: 10.0.3.1/24
├── 其他子网: 10.0.5.1, 10.0.7.1, 172.29.0.1, 172.30.0.1
├── WireGuard: 10.77.77.6
│
└── helix-p4d-1 容器 (bridge 网络)
    ├── 容器 IP: 动态分配 (docker bridge)
    ├── P4PORT: 1666/tcp
    ├── SSH: 22/tcp (未使用)
    └── 端口映射: host:32768 → container:1666
```

**客户端连接方式**:
- 外部: `192.168.50.2:32768`（局域网）
- 容器网络: `10.0.3.1:1666`（Docker 内部）
- P4V 客户端: `pc_qnap_depot_9516`（admin 用户，Windows P4V 2025.2）

## 备份系统

### 备份脚本

**路径**: `/share/Container/backup_perforce.sh`

**流程**:
1. 文件锁 (`/share/Container/perforce_backup/.backup.lock.d/`)
2. 检测 P4ROOT
3. 在容器内创建 checkpoint: `p4d -r $P4ROOT -jc /data/master/checkpoints/p4_backup`
4. 验证 checkpoint: `p4d -jv <checkpoint_file>`
5. 停止容器 (`docker stop -t 120`)
6. `docker cp` 全量拷贝 `/data/master/root` → `/share/Container/perforce_backup/<timestamp>/data/`
7. 拷贝 checkpoints → `/share/Container/perforce_backup/<timestamp>/checkpoints/`
8. 启动容器
9. 生成 manifest

**备份位置**: `/share/Container/perforce_backup/<YYYYMMDD_HHMMSS>/`

### 最近备份

```
20260505_011122/
20260505_011531/
20260628_161109/   ← 刚才我们的分析期间创建的
perforce/          ← 早期全量备份
```

## 历史事件

### 2024-10-19: 初次创建
容器通过 Container Station 创建，使用 `hawkmothstudio/helix-p4d:latest-data-4` 镜像。

### 2025-08-09: 最后一次成功 Checkpoint
checkpoint.1 和 journal.0 均为此时创建。此后 journal 持续增长到 1.7GB。

### 2026-06-17: 最后一次客户端活动
日志显示 `pc_qnap_depot_9516` (admin) 在 19:08 执行了 `user-fstat` 和 `user-reconcile` 操作。这是最后一次有记录的 P4 活动，距今 11 天。

### 2026-06-28: 容器频繁崩溃
当天启动 5 次，每次都只存活 5-6 分钟即 Exit 137 崩溃。健康检查在成功运行期间显示 `p4 info` 正常（Server uptime 37s-2m37s）。

## 健康检查日志样本

健康检查 (`p4 info`) 成功输出示例：

```
User name: p4admin
Client name: helix-p4d-1
Client host: helix-p4d-1
Server address: localhost:1666
Server root: /data/master/root
Server date: 2026/06/28 08:12:18 +0000 UTC
Server uptime: 00:01:37
Server version: P4D/LINUX26X86_64/2022.2/2407422 (2023/02/14)
Server license: none
Case Handling: sensitive
```

## 恢复流程

### 场景 A: 容器可以启动但频繁 OOM

1. 停止无关容器
2. 降低 p4d 内存限制 (`docker update --memory 3g --memory-swap 12g`)
3. 启动后立即 checkpoint 以截断 journal

### 场景 B: 数据损坏，需要从备份恢复

1. 停止容器: `docker stop helix-p4d-1`
2. 备份当前损坏数据: `mv /share/Container/perforce /share/Container/perforce.broken`
3. 选择最近的备份: `ls -lt /share/Container/perforce_backup/`
4. 恢复数据: `cp -a /share/Container/perforce_backup/<timestamp>/data /share/Container/perforce`
5. 启动容器: `docker start helix-p4d-1`
6. 回放 journal: `docker exec -u perforce helix-p4d-1 p4d -r /data/master/root -jr /data/master/root/journal.0`

### 场景 C: 从 checkpoint 恢复

1. 停止容器
2. 清空数据目录（保留 backup）
3. 用 checkpoint 重建: `docker exec -u perforce helix-p4d-1 p4d -r /data/master/root -jr /path/to/checkpoint.ckp.xxx`

### 场景 D: 完全重建

1. 如果 Depot 完好，可用 checkpoint 重建 metadata
2. `p4d -r <new_root> -jr checkpoint_file` 恢复 metadata
3. 将 depot 目录链接或拷贝到新 root 下

## 注意事项

1. **许可证**: 当前 `Server license: none`（免费版 5 用户/20 workspace），如需扩展需要购买 Helix Core 许可证
2. **安全等级**: security=2（需要 ticket 认证）
3. **Unicode 模式**: 已启用（`P4D_USE_UNICODE=true`）
4. **文件锁绕过**: `filetype.bypasslock=1`（为 Swarm 设置，但 Swarm 未实际部署）
5. **拓扑**: 单服务器（未配置 commit/edge server），ServerID 未设置
6. **Journal 截断**: checkpoint 后 journal.0 被清空但文件保留，新 journal 记录到新文件
7. **QNAP Container Station**: 容器由 Container Station 管理，可通过 GUI 或 `docker` CLI 操作
