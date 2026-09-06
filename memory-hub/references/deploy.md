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
- 不要在对话中回显 `.env` 全文（当前无 secret，但生产会加 API key）。
- Memory Hub **不接受** `NEO4J_URI`、Neo4j 用户名/密码；它只通过 Graphiti HTTP 访问后端。
- 非 development/test 环境强制账号认证（`mhu_` token）；`MEMORY_HUB_API_KEY` 仅为 legacy 共享 key（`legacy_api_key_enabled=true` 才可用，账号体系上线后弃用）。

## 多用户账号体系（认证 / 授权 / 历史接管）

> 权威设计见仓库 `docs/MULTI_USER_AUTH.md`；本节只记运维关键点。

### 三个环境标识作用域不同（勿混用）

| 变量 | 读它的进程 | 作用 |
|---|---|---|
| `ENVIRONMENT` | Hub :9287（`src/memory_hub/config.py`） | 非 development/test 时强制账号认证（无 token → 401） |
| `DASHBOARD_ENVIRONMENT` | Dashboard BFF :9288（`backend/dashboard_backend/config.py`，前缀 `DASHBOARD_`） | 非 development/test 时强制登录；否则无 token 回退 dev admin，前端**不弹登录页** |
| `MEMORY_HUB_ENV` | 仅 skill 层标记，代码不读 | `release`/`dev` 区分机器角色 |

Hub 与 Dashboard 是两个独立进程、各读各的 env 前缀。改 `ENVIRONMENT=release` 只约束 Hub 数据面；
面板登录必须单独设 `DASHBOARD_ENVIRONMENT=release`。

### 认证三模式与 token 类型

`authenticate_principal` 依次尝试：账号 token（`mhu_` 前缀）→ legacy 共享 key → dev 自报（无 Authorization，仅 development/test）。

| token 类型 | 来源 | 权限 |
|---|---|---|
| `agent` | `admin create-token` | 数据面写（sessions/memories/files）+ 检索 |
| `session` | 口令登录 `/auth/login` | 数据面只读 + 账号管理（`require_admin_session` 要求 session 型） |

agent token 调 `/v1/admin/*` 一律 403；账号管理走 CLI 或浏览器登录的 session token。

### 账号 bootstrap 与历史数据接管

`create_account` 在 username 命中既有历史 user_id（sessions/memories 有数据）时抛
`ADOPTION_CONFIRM_REQUIRED`（409），除非传 `adopt_existing=True`。bootstrap 管理员（默认 `sunlaibing`）
语义是初始 admin 接管全部历史资源，必须 `adopt_existing=True`，否则 gunicorn worker 启动即崩。

```bash
.venv/bin/python -m memory_hub.cli admin bootstrap                        # 建初始 admin（主 user_id = username，adopt 全部历史）
.venv/bin/python -m memory_hub.cli admin bind-user-id <u> <历史user_id> --yes  # 额外历史 user_id 绑定（接管其数据）
.venv/bin/python -m memory_hub.cli admin reconcile-ownership              # 回填 project 所有权
.venv/bin/python -m memory_hub.cli admin create-token <u> --label pi-cli  # 发 agent token（明文只打印一次）
```

`reconcile_ownership`：project 的唯一 user_id 已绑定某账号 → 自动认领该账号；混杂/无主 →
`needs_review`（普通账号禁写，admin 面板 Projects 页签或 CLI transfer 裁定）。幂等，已认领的 project 跳过。

### 凭据放 `~/.env`（不入库）

`src/memory_hub/config.py` 读 `env_file=(".env", "~/.env")`。凭据（`MEMORY_HUB_BOOTSTRAP_ADMIN_PASSWORD`、
`MEMORY_HUB_API_KEY` 等）只写 `~/.env`；项目 `.env` 无 secret 可入 git。

## 启动

### 一键脚本（推荐，NAS 常驻）

仓库自带幂等脚本（任意目录可执行，自动 cd 到仓库根）：

```bash
scripts/start_all.sh   # 启动 Hub(:9287) + Dashboard(:9288，含前端静态托管)，已运行则跳过
scripts/status.sh      # 进程/端口/健康总览（含上游 Graphiti :8005 探测）
scripts/stop_all.sh    # 停止全部
```

- pid 文件在 `data/run/*.pid`，日志：Hub → `data/memory-hub.log`，Dashboard → `data/dashboard.log`。
- Dashboard 前端无需单独启动：`frontend/dist` 由 dashboard backend 静态托管（:9288）。

### 开机自启（NAS 重启自动拉起）

链路：QTS → Container Station 拉起 memory-center 容器（docker `restart: unless-stopped`）
→ Entware qpkg（已启用）→ `/opt/etc/init.d/S99memory-hub` → `scripts/boot_start.sh`
**轮询等 Graphiti(:8005) healthy（最多 10 分钟，5s 间隔）** → `start_all.sh`。
超时仍启动（写入会先进 outbox 降级）。启动日志：`data/boot.log`。

```bash
# 一次性安装（需 admin/sudo 密码，agent 无权限写 /opt/etc/init.d）
sh scripts/install_autostart.sh
# 卸载
sh scripts/uninstall_autostart.sh
# 手动控制（安装后）
/opt/etc/init.d/S99memory-hub {start|stop|restart}
```

### 开发模式（web + outbox worker 一体，最简单）

```bash
cd /share/Container/memory-hub
.venv/bin/memory-hub serve
```

默认监听 `http://127.0.0.1:9287`，进程内启动 outbox worker（`ENABLE_OUTBOX_WORKER=true`）。

### 后台启动（NAS 上常驻）

> 推荐直接用 `scripts/start_all.sh`（幂等 + pid 管理 + 健康等待），以下是手动方式：

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

## SCHEMA_VERSION 迁移发布的额外门禁（用户定版）

涉及 SCHEMA_VERSION bump 的发布，在通用「更新发布」流程上固定加三步；全程禁 delete/reingest/reset/改配置：

1. **pull 前先备份 DB**：`cp data/memory-hub.sqlite3 data/memory-hub.sqlite3.bak.$(date +%F_%H%M%S)`，回执只报备份路径和大小。
2. **测试门禁**：`.venv/bin/pytest tests/unit/test_retrieval_fts.py tests/unit/test_retrieval_judge.py tests/unit/test_review_llm_client.py tests/unit/test_database_migrations.py -q` + `.venv/bin/python -m compileall -q src tests scripts`；任一失败即停，不进入重启。
   - NAS 环境注记：裸 `.venv/bin/pytest` 需 `PYTHONPATH=.` 才能 import 项目包；NAS `/tmp` 是 64MB tmpfs 易满（sqlite 报 disk 类错误），pytest 加 `--basetemp=<大容量路径>`——**适用于 NAS 上一切 pytest 运行、不限迁移门禁**（2026-09 一次普通增量发布门禁同样两连失败，报错 `database or disk is full` 与代码无关，清 /tmp 残留 + `--basetemp`/TMPDIR 指大盘后稳定全绿）；graphiti overlay 有变更时 compileall 目标追加 `deploy/graphiti-0.22.0`。pytest console script（`.venv/bin/pytest`）曾出现 collection quirk，遇到时改用 `.venv/bin/python -m pytest`（ce3efee 发布实证，测试本身全绿）。
3. **重启后只读验证迁移生效**：`schema_migrations` 表最新版本 == 目标版本、新增列存在（如 v7 的 `retrieval_judgments.intent`），再跑 `health/live` + `health/ready`。

**验收失败只完整回报证据，不回滚、不自行改代码/配置后继续**——修复/跳过由用户决策。

## Graphiti overlay（deploy/graphiti-0.22.0）变更的部署

Graphiti 服务（:8005）跑在 memory-center docker 容器里，自定义端点（/search-v2、/curate/*、
/resolve-entities、/get-memory）以 patches 文件形式注入容器，运行实体在 NAS 的
`memory_center/memory-center/patches/`。仓库 `deploy/graphiti-0.22.0/` 是 patches 的源码权威，
**两边不会自动同步**：只 push 仓库不拷 patches，容器跑的还是旧代码；`stop_all.sh/start_all.sh`
只重启 hub/dashboard/worker 三进程，**不碰 graphiti 容器**。

overlay 变更的发布步骤（插在通用流程的 stop/start 环节）：

1. 备份现 patches：`cp patches/retrieve.py patches/retrieve.py.bak.$(date +%Y%m%d%H%M%S)`（dto 等同理）
2. 拷贝仓库 `deploy/graphiti-0.22.0/` 对应文件覆盖 patches/
3. memory-center 目录下 `docker compose restart graphiti`，等 healthy（~10s）
4. 直接打 :8005 的变更端点凒烟（如 `POST /resolve-entities`），别只信 hub /health/ready——它只探活不验端点版本

## 排障

| 症状 | 排查 |
|---|---|
| `Permission denied` 执行 `.venv/bin/python` | venv 是坏拷贝，按上文重建 |
| 端口 9287 起不来 / `Address already in use` | `ss -tlnp \| grep 9287` 找占用者 |
| `/health/ready` 里 `graphiti:false` | `curl -sS http://10.77.77.6:8005/healthcheck`；确认网络可达 |
| 日志无 `outbox worker started` | worker 没起来，检查 `ENABLE_OUTBOX_WORKER` |
| memory 一直 `pending` | outbox worker 未运行或 Graphiti 投递失败，查日志 |
| memory 变 `failed` | 看 `error_code`，常见 group_id 非法 / Graphiti 永久错误 |
| 大批 memory 卡 `submitted`，outbox `confirm_episode` 反复 retry「episode is not indexed yet」 | Graphiti 侧 episode 丢失（如其内存队列随容器重启清空）：把事件重置回投递阶段重放，见下文「outbox 重投递」 |
| data 写到奇怪的地方 | 没从项目目录启动，`.env` 相对路径失效 |

### outbox 重投递（Graphiti 丢失 episode 后的恢复）

症状：memory 状态 `submitted` 但永不变 `indexed`，outbox 里 `graphiti.confirm_episode`
事件 `last_error = episode is not indexed yet`。原因：投递已成功（202），但 Graphiti
的 ingest 队列是内存态，容器重启后未处理的 episode 丢失，确认环节永远查不到。

恢复（payload 不变，把事件打回 `add_episode` 阶段重投，Graphiti 侧 uuid 幂等）：

```bash
cd /share/Container/memory-hub
cp data/memory-hub.sqlite3 data/memory-hub.sqlite3.bak.$(date +%F_%H%M%S)   # 先备份
.venv/bin/python - << 'EOF'
import sqlite3
from datetime import datetime, timezone
db = sqlite3.connect('data/memory-hub.sqlite3')
now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
cur = db.execute(
    """UPDATE outbox
       SET event_type='graphiti.add_episode', status='retry', attempt_count=0,
           next_attempt_at=?, lease_until=NULL, last_error=NULL, updated_at=?
       WHERE event_type='graphiti.confirm_episode' AND status='retry'""",
    (now, now),
)
db.commit()
print(f'reset {cur.rowcount} events')
EOF
```

无需重启：进程内 outbox worker（`OUTBOX_POLL_SECONDS=1`）会立即开始重投。
投递快（POST 202），瓶颈在 Graphiti 串行抽取（~35-70s/episode），几百条需数小时，
用 `scripts/status.sh` 或 dashboard :9288 的 Memories/Outbox 页签观察 `indexed` 增长即可。

### 默认 user_id（多用户）

hook 端默认 user_id 解析顺序：环境变量 `MEMORY_HUB_CLIENT_USER_ID` /
`MEMORY_HUB_USER_ID` → 团队当前成员 → 本机 profile
`~/.local/state/memory-hub-hook/client-profile.json`（已统一为 sunlaibing）。
服务端对不带 `X-User-Id` 的旧客户端回退 agent_id。
user scope 记忆落在 Graphiti group `user:{user_id}`。

### user 身份归一迁移（改 user_id 时的完整 SOP）

改 user_id 涉及三个存储面，缺一不可：

| 层 | 工具 | 覆盖 |
|---|---|---|
| Hub SQLite | `scripts/migrate_user_identity.py`（仅标准库；默认 dry-run，`--apply` 才写；自动 `.bak` 备份 + 单事务） | sessions/memories/files 的 user 字段、users 表合并、memories 与 graphiti_cleanup 的 `user:<old>` group 改名、**outbox 未完结事件 payload_json 文本替换** |
| Neo4j | 只能 `docker exec <neo4j> cypher-shell` 执行 `SET n.group_id`（节点和关系两条）；REST 无改 group 端点，**cypher-ro 网关是只读的，不能用于改名** | graph 侧 user scope 数据 |
| 各机 hook 身份 | `client-profile.json` + `~/.profile` 的 `MEMORY_HUB_CLIENT_USER_ID`（安装器以标记块写入） | 不改则旧 user 分组会随下一次写入复活 |

```bash
cd /share/Container/memory-hub
for OLD in <old-id...>; do
  python3 scripts/migrate_user_identity.py data/memory-hub.sqlite3 --from "$OLD" --to <new-id> --apply
done
```

验证：旧身份在三张表零残留、users 表只剩新 id、Neo4j `user:*` 分组只剩新组、
以新 user 调 `/v1/memories/search` 能命中原 user scope 记忆。

## 内容清洗与图谱重建（维护操作）

Hub 投递 Graphiti 前会过一道内容清洗层 `strip_archival_boilerplate()`（service.py）：按模式剥掉归档摘要开头的元数据套话，只留知识正文进入抽取。当前覆盖三种前缀：`xx 会话归档，工作目录：…。`（legacy）、`xx 会话「标题」，工作目录：…。`、`xx 会话「标题」（日期，工作目录：…）。`。新前缀出现时在此加模式即可对存量内容生效——它作用于投递时刻而非写入时刻，改模式不需要回写 SQLite。

重建某 group 的图谱映射用服务端仓库 `scripts/reingest_group.py <group> [--noise-only] [--dry-run|--yes]`：删 episode（remove_episode 级联删派生边和独占实体）后把 SQLite 原记忆重入 outbox，episode uuid == memory_id 溯源不变。`--noise-only` 经 cypher-ro 反查命中噪声实体的 episode 定点重建（大 group 必用）。只处理 Hub 有记录的 episode，Graphiti 独有的只报告不删；级联删除会漏孤儿实体，重建后需按模式补一次终扫。事故全文：memory-center `incidents/2026-08-20-entity-extraction-noise.md`。

存量 exact 重复回收用 `scripts/dedup_exact_memories.py`（默认 dry-run 出 JSON 报告，`--yes --limit N` 才实际分批执行）：判重规则与写入侧 exact 门禁一致（同 tenant/user/物理 group、content_hash+正文相等，**不跨物理 group 折叠**）；keeper 选 indexed 优先（图谱零抖动），其余软删 + 关审核行 + 撤 outbox + 退役关系账本 + 删 episode（失败转 graphiti_cleanup 表）+ tombstone 审计，软合并可 unmerge 反转；幂等可重跑。为 2026-09-01 exact 门禁（db0da36）上线前的 651 条存量冗余而写，新部署后先 dry-run 看报告再 `--yes --limit 5` 小批验证。

## 观测面板（dashboard）部署

面板是独立服务（`backend/` + `frontend/dist/`），与主服务分离部署。`frontend/dist` **已不纳入 git 追踪**（自 commit 2c3b935），NAS 上有 node v22（`~/.local/bin/node`），需在 NAS 本地构建。

**部署顺序铁律（「更新发布前后端」）**：① 先 `git pull`（「更新」= 拉代码，最先做，漏掉只重启不算完成）→ ② 有冲突优先修复冲突 → ③ 本地有未提交改动，更新后及时 commit（不要等用户提醒）→ ④ 重构建前端 → ⑤ 重启验证。只有纯「重启」才只做最后一步。

```bash
cd /share/Container/memory-hub
git pull                                    # 拉取 backend/ 与 frontend/src/

cd frontend && npm ci && npm run build && cd ..   # 生成 frontend/dist（依赖未变可跳过 npm ci）

cd backend
uv venv .venv --python 3.12                 # 首次
uv pip install --python .venv/bin/python -e .

# 启动/重启（推荐用一键脚本，stop_all + start_all 会同时处理 Hub 与 dashboard）
sh scripts/stop_all.sh && sh scripts/start_all.sh
# 或手动：
ps aux | grep memory-hub-dashboard | grep -v grep
kill <旧PID> 2>/dev/null
cd backend && setsid .venv/bin/memory-hub-dashboard > ../data/dashboard.log 2>&1 < /dev/null &

curl -sS http://127.0.0.1:9288/api/v1/health/live
```

> Hub 与 dashboard 都是 editable 安装，纯代码变更重启即生效，无需 reinstall。浏览器如缓存旧 JS 需强刷。

浏览器访问 `http://10.77.77.6:9288/`。详细配置见仓库 `docs/DASHBOARD.md`。

## 运行测试（改代码后）

```bash
cd /share/Container/memory-hub
.venv/bin/pytest                # NAS 上需加 --basetemp=<大容量路径>（/tmp 仅 64MB tmpfs，见上文门禁注记）
.venv/bin/python -m compileall -q src tests
```

端到端测试用 Fake Graphiti，不污染真实中心服务。
