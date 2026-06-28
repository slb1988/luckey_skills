# HBS3 同步任务配置

> 数据来源: `CloudConnector3/config.db` (jobs 表) + `job_log.db`
> 查询时间: 2026-06-28

## 云端账号

| 账号 ID | 名称 | 类型 |
|---------|------|------|
| `9385788e-451b-11ec-857d-f65d767d0e2b` | OneDrive_382 | OneDrive |
| `76f8f508-9a46-11ec-bd27-f22ab8884012` | 百度网盘Vip | 百度网盘 |

## 任务列表

### 1. Perforce Sync ✅ 启用

| 属性 | 值 |
|------|-----|
| **UUID** | `c0b42617-99b3-11ef-9a0a-245ebe58b3ef` |
| **启用** | ✅ 是 |
| **类型** | sync |
| **账号** | 百度网盘Vip |
| **方向** | 本地 → 远程 (local2remote) |
| **操作** | copy（增量复制，`copy.update_only: true`） |
| **本地路径** | `Container/perforce` |
| **远程路径** | `/NasSync/PerforceBackup` |
| **冲突策略** | 覆盖远程 (replace_remote) |
| **调度** | 每天 04:00 (`0 4 * * *`) |
| **通知** | 仅失败 (`notify.job_fail: true`) |
| **BBR 加速** | ✅ 开启 |
| **并发传输** | 5 |
| **创建时间** | 2024-11-03 |

### 2. Two-way Sync ✅ 启用

| 属性 | 值 |
|------|-----|
| **UUID** | `1f6a4386-914d-11f0-893e-245ebe58b3ef` |
| **启用** | ✅ 是 |
| **类型** | sync |
| **账号** | 百度网盘Vip |
| **方向** | 双向 (twoway) |
| **本地路径** | `BaiduDisk/Sync` |
| **远程路径** | `/NasSyncNew` |
| **冲突策略** | 重命名本地 (rename_local) |
| **调度** | 手动 |
| **BBR 加速** | ✅ 开启 |
| **创建时间** | 2025-09-14 |

### 3. Two-way Sync 1 ❌ 禁用

| 属性 | 值 |
|------|-----|
| **UUID** | `43557ec6-451c-11ec-b9f0-f65d767d0e2b` |
| **启用** | ❌ 否 |
| **类型** | sync |
| **账号** | OneDrive_382 |
| **方向** | 双向 (twoway) |
| **本地路径** | `Documents/OneDriveDisk` |
| **远程路径** | `/OneDrive` |
| **冲突策略** | 重命名本地 (rename_local) |
| **调度** | 无 |
| **创建时间** | 2021-11-14 |

### 4. Two-way Sync Worked ❌ 禁用 (限速)

| 属性 | 值 |
|------|-----|
| **UUID** | `0b2502c6-9a47-11ec-bd27-f22ab8884012` |
| **启用** | ❌ 否 (`user_stop: true`) |
| **类型** | sync |
| **账号** | 百度网盘Vip |
| **方向** | 双向 (twoway) |
| **本地路径** | `BaiduDisk/BaiduDiskAutoSync` |
| **远程路径** | `/NasSync` |
| **冲突策略** | 重命名本地 (rename_local) |
| **调度** | 每天 19:00 (`0 19 * * *`) |
| **下载限速** | 2 MB/s (工作日 9:00-18:00) |
| **上传限速** | 5 KB/s (工作日 9:00-18:00) |
| **创建时间** | 2022-03-02 |

## 近期运行日志 (Perforce Sync)

```
2026-06-28 04:00:01  Started Sync job: "Perforce Sync"
2026-06-28 04:08:49  Finished Sync job: "Perforce Sync"
2026-06-27 04:00:02  Started Sync job: "Perforce Sync"
2026-06-27 04:08:32  Finished Sync job: "Perforce Sync"
2026-06-26 04:00:02  Started Sync job: "Perforce Sync"
2026-06-26 04:09:04  Finished Sync job: "Perforce Sync"
2026-06-25 04:00:01  Started Sync job: "Perforce Sync"
2026-06-25 04:08:56  Finished Sync job: "Perforce Sync"
2026-06-24 04:00:02  Started Sync job: "Perforce Sync"
2026-06-24 04:08:24  Finished Sync job: "Perforce Sync"
2026-06-23 04:00:01  Started Sync job: "Perforce Sync"
2026-06-23 04:08:31  Finished Sync job: "Perforce Sync"
2026-06-22 04:00:01  Started Sync job: "Perforce Sync"
2026-06-22 04:08:33  Finished Sync job: "Perforce Sync"
```

平均每次运行约 8 分钟，稳定无报错。

## 数据文件位置

| 文件 | 路径 |
|------|------|
| 任务配置 | `/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/config.db` → `jobs` 表 (key=UUID, value=JSON) |
| 账号配置 | 同上 `accounts` 表 |
| 运行日志 | `/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/job_log.db` → `job_logs` 表 |
| 历史记录 | `/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/job_history.db` |
| 单任务数据 | `/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/data/system/sync/<UUID>/` |
| 单任务 job.db | `.../sync/<UUID>/job.db` (sync_pairs, change_events, failure_events 等表) |

## 查看任务信息的命令

```bash
SQLITE=/share/CACHEDEV1_DATA/.qpkg/CacheMount/bin/sqlite3
DB=/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/config.db

# 列出所有任务
$SQLITE $DB "SELECT json_extract(value, '$.name'), json_extract(value, '$.enable') FROM jobs;"

# 查看某任务完整配置
$SQLITE $DB "SELECT value FROM jobs WHERE key='<UUID>';"

# 查看运行日志
LOGDB=/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/job_log.db
$SQLITE $LOGDB "SELECT datetime(date,'unixepoch','localtime'), message FROM job_logs WHERE job_id='<UUID>' ORDER BY date DESC LIMIT 20;"
```

## 命令行触发同步任务

### 可行性分析

HBS3 同步任务可以通过 CLI 主动触发，但需要理解其架构才能找到正确的方法。

**架构脉络**（发现过程）:

1. **hbs3-rr3c** — 底层工具，基于 rclone 定制。支持 `hbssync source:path dest:path`，但它需要 rclone 风格的配置文件 (`rr3c.conf`)，这个文件不存在于磁盘上（由 CloudConnector3 动态生成）。直接用 hbs3-rr3c 不行。

2. **RR2 Server** — 端口 38898，脚本 `rr2/scripts/rr2_client.sh` 有 `-startjob --qpkg <job_id>` 命令，但 RR2 server 配置文件 `rr2_server.conf` 中 `enable: false`（未启用），且 `rr2c_cli.py` 不存在（仅 .pyc）。此路不通。

3. **CloudConnector3 HTTP API** — 通过 Apache(5000端口) → FastCGI → Unix Socket 提供服务，路由为 `/cc3/v1/users/<user_id>/jobs`。需要 QTS Session 认证，但当前账户有 2FA 保护，无法通过命令行获取 Session。**sudo/su 环境下几乎不可能走通此路。**

4. **cc3-cli** — CloudConnector3 自带的命令行工具，但仅支持 `--list_account`、`--list_job`、`--report`，不支持 start/stop。

5. **✅ sync 命令**（最终方案） — CloudConnector3 的 `sync` 入口 (`qnap.cloudconnector3.sync.syncdaemon:main`) 接受 `config_db job_id {start,run,stop,scan,pid}` 参数，可直接在前台或后台运行同步任务。这是正确的方式。

**sync 子命令**:

| 子命令 | 说明 |
|--------|------|
| `run` | 前台运行，可看到实时日志输出 |
| `start` | 后台 daemon 模式运行 |
| `stop` | 停止 daemon |
| `scan` | 触发重新扫描本地/远程目录 |
| `pid` | 查看 daemon 进程 PID |

### 触发命令

**先决条件**:
- 必须以 `admin` 用户身份执行（apikey 文件 `600` 仅 admin 可读，数据库目录仅 admin 可写）
- 需要设置环境变量 `QPKG_HOME` 和 `QPKG_NAME`
- 数据库需要复制到可写位置（原始 config.db 所在目录不可写，APSW 需要 journal 写入权限）

**通用模板**:

```bash
# 1. 复制数据库到可写位置（每次执行都需要，因为 job.db 会更新）
cp /share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/config.db /tmp/cc3_config_sync.db

# 2. 以 admin 身份执行 sync
echo "<admin密码>" | sudo -S -u admin \
  env PYTHONPATH=/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/python/lib/python3.11/site-packages \
  PATH=/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/python/bin:$PATH \
  QPKG_HOME=/share/CACHEDEV1_DATA/.qpkg/HybridBackup \
  QPKG_NAME=HybridBackup \
  /share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/python/bin/sync \
  /tmp/cc3_config_sync.db \
  <JOB_UUID> \
  run
```

**实际执行 Perforce Sync**:

```bash
cd /share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3
cp /share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/config.db /tmp/cc3_config_sync.db

echo "MTs451Hi966jzN" | sudo -S -u admin \
  env PYTHONPATH=/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/python/lib/python3.11/site-packages \
  PATH=/share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/python/bin:$PATH \
  QPKG_HOME=/share/CACHEDEV1_DATA/.qpkg/HybridBackup \
  QPKG_NAME=HybridBackup \
  /share/CACHEDEV1_DATA/.qpkg/HybridBackup/CloudConnector3/python/bin/sync \
  /tmp/cc3_config_sync.db \
  c0b42617-99b3-11ef-9a0a-245ebe58b3ef \
  run
```

### 已知问题

- **远程路径丢失**: 上次（2026-06-28 21:48/21:54）手动执行时，百度网盘返回 `errno: -9`，即 `/NasSync/PerforceBackup` 目录不存在。可能被误删除或移动。
- **需要以 admin 身份**: 普通用户无权限读取 `/tmp/.cloudconnector/` 下的 apikey 文件（`600`）。
- **config.db 路径**: APSW SQLite Wrapper 要求数据库所在目录可写（需要创建 journal/WAL 文件）。原路径 `CloudConnector3/` 目录为 755 且属主为 admin，其他用户无写权限。需复制到 `/tmp/` 等可写位置再执行。
