# Langfuse — LLM 可观测性平台

> 自部署于 `dev@auto-server`，Docker Compose 管理  
> 版本：Langfuse v3.174.1  
> 状态：✅ 运行中（2026-07-25 修复 worker 后）

## 目录

- 一、架构概览
- 二、连接信息
- 三、API 密钥与本地凭据
- 四、内部组件配置
- 五、业务接入指南
- 六、运维命令
- 七、故障记录
- 八、关键注意事项

---

## 一、架构概览

Langfuse v3 采用 **Web + Worker 分离架构**：Web 容器负责 UI 和 ingestion API 接入，Worker 容器负责消费队列写入 ClickHouse。两者必须同时运行，否则 trace 数据只进队列不出结果。

```
┌──────────────────────────────────────────────────────┐
│                   Langfuse Web UI                     │
│              http://192.168.2.13:3030                 │
└──────────┬──────────────────────┬────────────────────┘
           │                      │
┌──────────▼──────────┐  ┌───────▼─────────────────────┐
│  langfuse (Web)      │  │  langfuse-worker            │
│  langfuse/langfuse:3 │  │  langfuse/langfuse-worker:3 │
│                      │  │                             │
│  • 接收 trace 事件    │  │  • 消费 BullMQ 队列          │
│  • 写入 Redis 队列    │  │  • 读取 MinIO 事件文件       │
│  • 写入 MinIO         │  │  • 写入 ClickHouse           │
└──────────┬──────────┘  └───────┬─────────────────────┘
           │                      │
           └──────────┬───────────┘
                      │
        ┌─────────────┼─────────────────┐
        │             │                  │
   postgres       clickhouse          redis
   (元数据)        (分析存储)          (队列/缓存)
                       │
                    minio
                 (事件文件存储)
```

**Ingestion 处理链路**：
```
Client SDK → POST /api/public/ingestion → Web 服务器
  → BullMQ 队列 (otel-ingestion-queue)
  → MinIO (事件 JSON: otel/<project>/YYYY/MM/DD/HH/mm/uuid.json)
  → Worker 消费队列, 读 MinIO, 写 ClickHouse
```

| 容器 | 镜像 | 端口 (宿主机) | 说明 |
|------|------|--------------|------|
| `langfuse` | `langfuse/langfuse:3` | `3030:3000` | Web UI + ingestion API |
| `langfuse-worker` | `langfuse/langfuse-worker:3` | — (内部) | **必须**：消费队列写入 ClickHouse |
| `langfuse-postgres` | `postgres:15-alpine` | — (内部) | 元数据 |
| `langfuse-clickhouse` | `clickhouse/clickhouse-server` | — (内部) | 分析数据（traces/observations/scores） |
| `langfuse-redis` | `redis:7` | — (内部) | BullMQ 队列 + 缓存 |
| `langfuse-minio` | `minio/minio` | `9092:9000`, `9093:9001` | 事件文件 + 媒体存储 |

---

## 二、连接信息

### 2.1 Langfuse Web UI

| 项目 | 值 |
|------|-----|
| 局域网地址 | `http://192.168.2.13:3030` |
| 本地地址 | `http://localhost:3030` |
| 管理员邮箱 | `sunlaibing88@gmail.com` |
| 管理员密码 | `${LANGFUSE_ADMIN_PASSWORD}` |
| 组织名 | Default (`org-default`) |
| 项目名 | Default (`proj_default`) |

### 2.2 MinIO Console（对象存储管理）

| 项目 | 值 |
|------|-----|
| 地址 | `http://192.168.2.13:9093` |
| 用户名 | `minio` |
| 密码 | `${LANGFUSE_MINIO_PASSWORD}` |

---

## 三、API 密钥（用于业务接入）

> 密钥在 Project Settings → API Keys 中获取或通过数据库创建。实际值只存本 skill 目录的 `.env`，下表及密码表只给出变量名。

首次配置时复制 `../.env.example` 到 `../.env` 并在本地填写，保留已有文件；`.env` 不入 Git。API 密钥与管理员、内部组件、安全密钥都保存在这里，但应用只应注入自己需要的变量，不能把整份运维凭据注入业务容器。

Agent 从 skill 目录调用 `python ~/.agent-hooks/env-read-guard/guard.py keys` 只查看变量名，实际使用走 `pipe KEY -- <静默下游命令>`。不要直接读文件、打印密钥、开 shell trace 或把值写进报告。

### API 变量

| 用途 | 值 |
|------|-----|
| **Public Key** | `${LANGFUSE_PUBLIC_KEY}` |
| **Secret Key** | `${LANGFUSE_SECRET_KEY}` |
| **Host** | `http://192.168.2.13:3030` 或 `http://localhost:3030` |

> ⚠️ 如需在 Docker 容器内访问 Langfuse，请使用桥接网络 IP 或 `host.docker.internal:3030`（需要 `extra_hosts` 配置）。

### 如何创建新密钥

通过 Langfuse Web UI：登录 → 选择项目 → Settings → API Keys → "Create API Key"

如果 Web UI 不可用，通过数据库创建（需要正确的 bcrypt 哈希和 fast hash）：

```python
import bcrypt, hashlib, os, uuid

# 1. 生成密钥对
pk = f"pk-lf-{uuid.uuid4()}"
sk = f"sk-lf-{uuid.uuid4()}"

# 2. hashed_secret_key = bcrypt(secret_key, rounds=11)
hashed = bcrypt.hashpw(sk.encode(), bcrypt.gensalt(rounds=11)).decode()

# 3. fast_hashed_secret_key = SHA256(salt + SHA256(secret_key).hex).hex
SALT = os.environ["SALT"]
fast_hash = hashlib.sha256(
    (SALT + hashlib.sha256(sk.encode()).hexdigest()).encode()
).hexdigest()

# 4. INSERT INTO api_keys (...)
```

---

## 四、内部组件配置（供运维参考）

### 4.1 PostgreSQL

| 项目 | 值 |
|------|-----|
| 容器内地址 | `langfuse-postgres:5432` |
| 数据库 | `langfuse` |
| 用户 | `postgres` |
| 密码 | `${LANGFUSE_POSTGRES_PASSWORD}` |

### 4.2 ClickHouse

| 项目 | 值 |
|------|-----|
| 容器内地址 | `langfuse-clickhouse:8123` (HTTP) / `:9000` (Native) |
| 用户 | `${LANGFUSE_CLICKHOUSE_PASSWORD}` |
| 密码 | `${LANGFUSE_CLICKHOUSE_PASSWORD}` |

### 4.3 Redis

| 项目 | 值 |
|------|-----|
| 容器内地址 | `langfuse-redis:6379` |
| 密码 | `${LANGFUSE_REDIS_PASSWORD}` |

### 4.4 安全密钥（NEXTAUTH / 加密）

| 密钥 | 值 |
|------|-----|
| `NEXTAUTH_SECRET` | `${NEXTAUTH_SECRET}` |
| `SALT` | `${SALT}` |
| `ENCRYPTION_KEY` | `${ENCRYPTION_KEY}` |

---

## 五、业务接入指南

### 5.1 Python 应用（RAGFlow / FastAPI / Flask / Django）

#### 环境变量方式

以下示例假定应用进程已注入 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`、`LANGFUSE_HOST`。普通 Python/Node 进程不会自动读取本 skill 的 `.env`；由应用配置加载器（如显式指定路径的 python-dotenv）或进程管理器注入，文件路径按部署环境设置。不要把密钥重新粘贴到代码。

Docker Compose 的 `.env` / `--env-file` 用于配置插值；只在服务 `environment` 中映射所需变量，不把整份文件作为业务容器的 `env_file`。

#### 代码方式

```python
import os
from langfuse import Langfuse

langfuse = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host=os.environ["LANGFUSE_HOST"]
)

# 记录 trace
trace = langfuse.start_observation(
    name="my-operation",
    as_type="span",
    input={"query": "用户输入"},
    metadata={"source": "ragflow"}
)

# ... 业务逻辑 ...

trace.update(output={"answer": "LLM 回复"})
trace.end()
langfuse.flush()
```

#### LiteLLM 配置（如使用 LiteLLM 代理）

```yaml
litellm_settings:
  success_callback: ["langfuse"]
  failure_callback: ["langfuse"]
```

在 LiteLLM 进程启动环境中注入上述三项 `LANGFUSE_*` 变量，配置文件只保留回调设置，不存凭据。

### 5.2 RAGFlow 配置

RAGFlow v0.26.4 接入 Langfuse，直接使用以下环境变量：

```yaml
# ragflow 服务添加环境变量
environment:
  LANGFUSE_PUBLIC_KEY: "${LANGFUSE_PUBLIC_KEY:?required}"
  LANGFUSE_SECRET_KEY: "${LANGFUSE_SECRET_KEY:?required}"
  LANGFUSE_HOST: "${LANGFUSE_HOST:?required}"
```

或在代码中手动集成：

```python
import os
from langfuse import Langfuse

langfuse = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host=os.environ["LANGFUSE_HOST"]
)
```

### 5.3 Node.js / TypeScript 应用

```bash
npm install langfuse
```

```typescript
import { Langfuse } from "langfuse";

const langfuse = new Langfuse({
  publicKey: process.env.LANGFUSE_PUBLIC_KEY,
  secretKey: process.env.LANGFUSE_SECRET_KEY,
  baseUrl: process.env.LANGFUSE_HOST,
});

const trace = langfuse.trace({ name: "my-trace" });
// ...
await langfuse.shutdownAsync();
```

### 5.4 容器内访问注意事项

> ✅ **已修复 (2026-07-24)**：Docker iptables NAT 规则已补全，容器现在可以通过 `192.168.2.13:3030` 正常访问 Langfuse。
> ⚠️ **注意 (2026-07-25)**：`docker compose down/up` 后容器 IP 可能变化，NAT 规则会失效。同网络容器优先用容器名直连。

| 场景 | Host 配置 | 说明 |
|------|----------|------|
| 同 Docker 网络容器（推荐） | `http://langfuse:3000` | 走 Docker 内部 DNS，无 NAT 依赖 |
| 容器内访问（外部 IP） | `http://192.168.2.13:3030` | 需要 iptables NAT 规则 |
| 宿主机本地 | `http://localhost:3030` | 宿主机直接访问 |
| 局域网其他机器 | `http://192.168.2.13:3030` | 外部机器访问 |

**同网络直连原理**：RAGFlow 和 Langfuse 都在 `docker_default` 网络（172.20.0.0/16），容器名 `langfuse` 可被同一网络的容器直接解析，端口为容器内部端口 `3000`（非宿主机映射的 3030）。

### 5.5 验证连接

通过已注入环境变量的应用执行，只回报鉴权结果，不输出凭据或配置对象：

```python
import os
from langfuse import Langfuse
l = Langfuse(
    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
    host=os.environ["LANGFUSE_HOST"]
)
print(l.auth_check())
```

---

## 六、运维命令

```bash
# 查看状态（6 个容器）
cd /mnt/disk2/langfuse && docker compose ps

# 查看日志
cd /mnt/disk2/langfuse && docker compose logs -f        # 所有容器
docker logs langfuse --tail 100                          # 仅 Web
docker logs langfuse-worker --tail 100                   # 仅 Worker

# 重启全部服务
cd /mnt/disk2/langfuse && docker compose restart

# 重建并启动（修改 docker-compose.yml 后）
cd /mnt/disk2/langfuse && docker compose up -d

# 仅重建某个服务
cd /mnt/disk2/langfuse && docker compose up -d langfuse-worker

# 停止
cd /mnt/disk2/langfuse && docker compose down

# 进入 PostgreSQL
docker exec -it langfuse-postgres psql -U postgres -d langfuse

# 队列积压检查（已安全注入 LANGFUSE_REDIS_PASSWORD）
REDISCLI_AUTH="$LANGFUSE_REDIS_PASSWORD" docker exec -e REDISCLI_AUTH langfuse-redis \
  redis-cli LLEN 'bull:otel-ingestion-queue:wait'
# 返回值 > 0 且不减少 → worker 没在消费

# ClickHouse 数据量检查
docker exec langfuse-clickhouse clickhouse-client \
  -q "SELECT count() FROM traces"
docker exec langfuse-clickhouse clickhouse-client \
  -q "SELECT count() FROM observations"

# 配置文件位置
# docker-compose.yml: /mnt/disk2/langfuse/docker-compose.yml
# 管理面板 HTML: /mnt/disk2/langfuse/index.html
# Docker 代理配置: /etc/systemd/system/docker.service.d/http-proxy.conf
```

### 诊断 trace 收不到

1. **检查 worker 是否运行**：`docker compose ps langfuse-worker`
2. **检查队列是否积压**：Redis `LLEN bull:otel-ingestion-queue:wait`
3. **检查 worker 日志**：`docker logs langfuse-worker --tail 50`
4. **检查 ClickHouse 是否写入**：`SELECT count() FROM traces`
5. **验证网络连通**：从业务容器 `curl http://192.168.2.13:3030/api/public/health`

---

## 七、故障记录

### 2026-07-25：Dashboard 页面 500（Widget Schema 不兼容）

**症状**：`/project/proj_default/dashboards` 报 `Internal error. Please check error logs`。

**原因**：数据库中 `langfuse-home-dashboard` 的 widget 使用了 `"type": "preset"`（新版 Langfuse 创建的），但当前 Web 镜像的 `DashboardDefinitionWidgetSchema` 只接受 `"type": "widget"`（需要 `widgetId` 字段）。`Zod.parse()` 在整个列表上抛异常导致 API 500。

**修复**：删除不兼容的记录 `DELETE FROM dashboards WHERE id = 'langfuse-home-dashboard'`，或更新 image 到支持 preset 的版本。

### 2026-07-25：RAGFlow 连不上 Langfuse（容器名直连方案）

**症状**：RAGFlow 容器 `curl http://192.168.2.13:3030` 返回 `Connection refused`。

**原因**：`docker compose down/up` 后 Langfuse 容器 IP 变了（172.20.0.6 → 172.20.0.7），iptables 规则中硬编码的旧 IP 失效。

**修复**：RAGFlow 和 Langfuse 都在 `docker_default` 网络，改用容器名直连 `http://langfuse:3000`（内部端口），无需经过宿主机 NAT。
```sql
UPDATE tenant_langfuse SET host = 'http://langfuse:3000' WHERE tenant_id = '...';
```

### 2026-07-25：Trace 收不到（缺少 Worker 容器）

**症状**：Langfuse Web UI 显示 "Waiting for first trace"，但业务侧已配置密钥并发送数据。`curl` ingestion 端点返回 207，`auth_check()` 返回 True。

**原因**：Langfuse v3 的 `langfuse/langfuse:3` 镜像只包含 Web 服务，不包含队列消费逻辑。需要独立的 `langfuse/langfuse-worker:3` 镜像。缺少 Worker 时，ingestion 事件被写入 Redis BullMQ 队列和 MinIO，但无人消费写入 ClickHouse。

**诊断方法**：
```bash
# 队列积压量（>0 且不动 = worker 没运行）
REDISCLI_AUTH="$LANGFUSE_REDIS_PASSWORD" docker exec -e REDISCLI_AUTH langfuse-redis \
  redis-cli LLEN 'bull:otel-ingestion-queue:wait'
# ClickHouse 空
docker exec langfuse-clickhouse clickhouse-client -q "SELECT count() FROM traces"
```

**修复**：
1. 修复 Docker 代理（systemd override: `/etc/systemd/system/docker.service.d/http-proxy.conf` → `HTTP_PROXY=http://192.168.2.70:7897`）
2. `docker pull langfuse/langfuse-worker:3`
3. 在 `docker-compose.yml` 添加 `langfuse-worker` 服务（与 Web 共享相同环境变量）
4. `docker compose up -d langfuse-worker`

**结果**：Worker 启动后自动消费积压队列，ClickHouse 在 30 秒内写入全部历史 trace。

### 2026-08-05：Dashboard 500 / scores.all 报 Internal Error（ClickHouse 版本漂移）

**症状**：Dashboard 页面报 `Internal error. Please check error logs`，Web 日志显示 `tRPC route failed on scores.all`，ClickHouse 报 `Not found column and(equals(...))`。

**原因**：`docker-compose.yml` 中 ClickHouse 使用 `clickhouse/clickhouse-server`（无版本 pin），镜像已升级到 26.7.x。Langfuse `:3` 浮动标签的旧镜像内置的 ClickHouse 查询构建器生成的 SQL 被新版 ClickHouse 解析器拒绝。两个浮动标签的漂移方向不一致时触发。

**修复**：拉取最新 Langfuse 镜像并重建 Web + Worker：
```bash
HTTP_PROXY=http://192.168.2.70:7897 HTTPS_PROXY=http://192.168.2.70:7897 \
  docker pull langfuse/langfuse:3 langfuse/langfuse-worker:3
cd /mnt/disk2/langfuse && docker compose up -d langfuse langfuse-worker
```

**根本缓解**：在 `docker-compose.yml` 中固定 ClickHouse 版本（如 `clickhouse/clickhouse-server:24.8`）或使用 Langfuse 的 digest pin，避免两个组件独立漂移。

### 2026-07-24：Langfuse 启动失败（缺少 PostgreSQL）

**症状**：`langfuse` 容器反复重启，日志报 `Can't reach database server at db_postgres:5432`

**原因**：`docker-compose.yml` 引用外部 PostgreSQL `db_postgres`，但该容器不存在。

**修复**：
1. 在 `docker-compose.yml` 中添加 `langfuse-postgres` 服务（使用本地已有镜像 `postgres:15-alpine`）
2. 将 `DATABASE_URL` 改为 `langfuse-postgres:5432`
3. 添加 `depends_on` 健康检查依赖
4. `docker compose up -d` 重建

**结果**：全部服务恢复正常。

---

## 八、关键注意事项

1. **凭据安全**：所有实际凭据只存本地 `.env` 或密钥管理服务，不提交到 Git、不打印；已入 Git 历史的密钥应安排轮换，迁出当前文件不等于清除了历史。
2. **PostgreSQL 持久化**：数据存储在 `postgres-data` Docker Volume 中，备份时注意备份该卷。
3. **网络**：Langfuse 使用外部网络 `docker_default`（`external: true`），新服务需要加入此网络才能用容器名通信。
4. **SALT 的重要性**：`SALT` 从受控环境注入，用于生成 `fast_hashed_secret_key`，修改它会导致所有 API 密钥失效。迁移凭据存储位置不等于授权更改服务器的 SALT。
5. **密码初始化**：`LANGFUSE_INIT_USER_PASSWORD` 仅在首次启动时生效，数据库已有用户后不再自动更新。
6. **镜像版本漂移**：`langfuse/langfuse:3` 和 `clickhouse/clickhouse-server` 均为浮动标签，各自独立升级。ClickHouse 大版本升级后 Langfuse 查询构建器可能生成不兼容的 SQL（典型症状：`tRPC route failed on scores.all` + ClickHouse `Not found column`）。建议固定 ClickHouse 版本号或用 digest pin 绑定两个镜像的兼容版本对。
