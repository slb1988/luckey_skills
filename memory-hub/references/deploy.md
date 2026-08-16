# Memory Hub 部署与运维

本文件覆盖 Memory Hub 的安装、启动、重启、备份与排障。使用说明见 [../SKILL.md](../SKILL.md)。

## 前置条件

- Linux（QNAP NAS）或 macOS，Python 3.11+（本机实际用 3.12）。
- 能访问 `http://10.77.77.6:8005`（上游 Graphiti）。
- 已安装 `uv`（可选，重建 venv 用）或可用 `python3 -m venv`。

## 项目目录与文件

```text
/share/Container/memory-hub/
├── .venv/                 # 虚拟环境（Linux Python 3.12）
├── .env                   # 环境配置（无 secret）
├── src/memory_hub/        # 源码
├── data/
│   ├── memory-hub.sqlite3 # metadata DB
│   ├── session-files/     # 不可变 session 文件存储
│   └── memory-hub.log     # 运行日志
├── config/env.example     # 配置模板
└── docs/                  # 设计/接口/运维文档
```

## 安装（首次 / venv 重建）

### 关键坑：macOS venv 在 NAS 上不可用

这个项目原本在 macOS（`/Users/sun/Documents/workspace/memory-hub`）开发，`.venv` 是被整目录拷贝过来的。在 NAS 上它**完全损坏**：
- `pyvenv.cfg` 指向 `/Library/Frameworks/Python.framework/...`（macOS 路径）。
- `bin/python` 等是损坏的普通文件（不是符号链接），执行报 `Permission denied`。

所以不要直接 `source .venv/bin/activate`，必须先重建。

### 用 uv 重建（推荐）

```bash
cd /share/Container/memory-hub
# 备份旧的坏 venv（确认无用后删除）
mv .venv .venv.bak-macos

# 用本机 Python 3.12 重建 + 安装
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -e .
```

安装 `[dev]` 依赖（跑测试才需要）：

```bash
uv pip install --python .venv/bin/python -e '.[dev]'
```

### 用标准 venv 重建（无 uv 时）

```bash
cd /share/Container/memory-hub
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e '.[dev]'
```

验证：

```bash
.venv/bin/memory-hub --help
# 应输出 {serve,worker,agent} 子命令
```

## 配置（.env）

当前 `.env`（development，无 secret）：

```dotenv
GRAPHITI_BASE_URL=http://10.77.77.6:8005
GRAPHITI_CONNECT_TIMEOUT_SECONDS=3
GRAPHITI_READ_TIMEOUT_SECONDS=30

METADATA_DATABASE_PATH=./data/memory-hub.sqlite3
FILE_STORE_BACKEND=filesystem
FILE_STORE_ROOT=./data/session-files

MAX_SESSION_FILE_BYTES=104857600        # 100 MiB
MAX_DECOMPRESSED_FILE_BYTES=262144000   # 250 MiB
MAX_API_JSON_BYTES=65536
UPLOAD_URL_TTL_SECONDS=600
IDEMPOTENCY_TTL_DAYS=30

HOST=127.0.0.1
PORT=9287
ENVIRONMENT=development
# MEMORY_HUB_API_KEY=replace-in-non-development

ENABLE_OUTBOX_WORKER=true
OUTBOX_POLL_SECONDS=1
OUTBOX_MAX_ATTEMPTS=12
OUTBOX_MAX_BACKOFF_SECONDS=300
```

要点：
- 所有 `./data` 路径是**相对路径**，必须从项目目录启动。
- Memory Hub **不接受** `NEO4J_URI`、Neo4j 用户名/密码；它只通过 Graphiti HTTP 访问后端。
- 非 development/test 环境必须设置 `MEMORY_HUB_API_KEY`。

## 启动

### 开发模式（web + outbox worker 一体，最简单）

```bash
cd /share/Container/memory-hub
.venv/bin/memory-hub serve
```

默认监听 `http://127.0.0.1:9287`，进程内启动 outbox worker（`ENABLE_OUTBOX_WORKER=true`）。

### 后台启动（NAS 上常驻）

`nohup` 在本机不存在，用 `setsid`：

```bash
cd /share/Container/memory-hub
setsid .venv/bin/memory-hub serve > data/memory-hub.log 2>&1 < /dev/null &
echo $!   # 记下 PID
```

### 生产进程模式（web 与 worker 分离）

Web 进程（关掉进程内 worker）：

```bash
cd /share/Container/memory-hub
ENABLE_OUTBOX_WORKER=false \
  .venv/bin/gunicorn 'memory_hub.app:create_app()' \
  --bind 0.0.0.0:9287 --workers 2 --threads 4 --timeout 120
```

独立 worker：

```bash
cd /share/Container/memory-hub
.venv/bin/memory-hub worker
```

> SQLite 只适合单机开发/试运行；多副本生产前先切 PostgreSQL（adapter 待实现）。不要让多台机器共享同一个 SQLite 文件。

## 健康检查

```bash
curl -sS http://127.0.0.1:9287/health/live
curl -sS http://127.0.0.1:9287/health/ready
```

ready 正常返回：

```json
{"dependencies":{"graphiti":true,"metadata":true},"status":"ready","write_degraded":false}
```

- `dependencies.graphiti=false`：上游 Graphiti 不可用（写入仍可进 outbox，检索会 503）。
- `write_degraded=true`：写入降级，排查 outbox / metadata。

## 日志

```bash
tail -f /share/Container/memory-hub/data/memory-hub.log
```

正常启动应看到 `outbox worker started` + `Running on http://127.0.0.1:9287`。

## 停止 / 重启

```bash
# 找到进程
ps aux | grep 'memory-hub' | grep -v grep

# 停止（按 PID）
kill <PID>

# 重启（开发模式）
cd /share/Container/memory-hub
setsid .venv/bin/memory-hub serve > data/memory-hub.log 2>&1 < /dev/null &
```

## 备份

SQLite + 本地文件，直接停服快照即可（不需要 Neo4j 在线 dump 那套）：

```bash
cd /share/Container/memory-hub
kill <PID> 2>/dev/null; sleep 1
tar -czf /share/Container/memory-hub-backup-$(date +%F).tar.gz data/memory-hub.sqlite3 data/session-files .env
# 重新启动
setsid .venv/bin/memory-hub serve > data/memory-hub.log 2>&1 < /dev/null &
```

> 原始 session JSON 都在 `data/session-files/objects/`（按内容 SHA-256 去重），记忆/版本/幂等/outbox 元数据在 `data/memory-hub.sqlite3`。两者都要备份。

## 排障

| 症状 | 排查 |
|---|---|
| `Permission denied` 执行 `.venv/bin/python` | venv 是坏拷贝，按上文重建 |
| 端口 9287 起不来 / `Address already in use` | `ss -tlnp \| grep 9287` 找占用者 |
| `/health/ready` 里 `graphiti:false` | `curl -sS http://10.77.77.6:8005/healthcheck`；确认网络可达 |
| 日志无 `outbox worker started` | worker 没起来，检查 `ENABLE_OUTBOX_WORKER` |
| memory 一直 `pending` | outbox worker 未运行或 Graphiti 投递失败，查日志 |
| memory 变 `failed` | 看 `error_code`，常见 group_id 非法 / Graphiti 永久错误 |
| data 写到奇怪的地方 | 没从项目目录启动，`.env` 相对路径失效 |

## 运行测试（改代码后）

```bash
cd /share/Container/memory-hub
.venv/bin/pytest
.venv/bin/python -m compileall -q src tests
```

端到端测试用 Fake Graphiti，不污染真实中心服务。
