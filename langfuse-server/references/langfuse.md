# Langfuse — LLM 可观测性平台

> 自部署于 `dev@auto-server`，Docker Compose 管理  
> 版本：Langfuse v3.174.1  
> 状态：✅ 运行中（2026-07-25 修复 worker 后）

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
| 管理员密码 | `!hmR5h80bzH8ks4Z` |
| 组织名 | Default (`org-default`) |
| 项目名 | Default (`proj_default`) |

### 2.2 MinIO Console（对象存储管理）

| 项目 | 值 |
|------|-----|
| 地址 | `http://192.168.2.13:9093` |
| 用户名 | `minio` |
| 密码 | `miniosecret` |

---

## 三、API 密钥（用于业务接入）

> 以下密钥在 Project Settings → API Keys 中获取或通过数据库创建。

### 当前有效密钥

| 用途 | 值 |
|------|-----|
| **Public Key** | `pk-lf-ade6a02d-1393-4af4-9100-c755789722cc` |
| **Secret Key** | `sk-lf-a4850c13-3608-470f-a19e-6ee5f16c625b` |
| **Host** | `http://192.168.2.13:3030` 或 `http://localhost:3030` |

> ⚠️ 如需在 Docker 容器内访问 Langfuse，请使用桥接网络 IP 或 `host.docker.internal:3030`（需要 `extra_hosts` 配置）。

### 如何创建新密钥

通过 Langfuse Web UI：登录 → 选择项目 → Settings → API Keys → "Create API Key"

如果 Web UI 不可用，通过数据库创建（需要正确的 bcrypt 哈希和 fast hash）：

```python
import bcrypt, hashlib, uuid

# 1. 生成密钥对
pk = f"pk-lf-{uuid.uuid4()}"
sk = f"sk-lf-{uuid.uuid4()}"

# 2. hashed_secret_key = bcrypt(secret_key, rounds=11)
hashed = bcrypt.hashpw(sk.encode(), bcrypt.gensalt(rounds=11)).decode()

# 3. fast_hashed_secret_key = SHA256(salt + SHA256(secret_key).hex).hex
SALT = "1fddb49ee65746c08a46d4f54e338254"
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
| 密码 | `difyai123456` |

### 4.2 ClickHouse

| 项目 | 值 |
|------|-----|
| 容器内地址 | `langfuse-clickhouse:8123` (HTTP) / `:9000` (Native) |
| 用户 | `clickhouse` |
| 密码 | `clickhouse` |

### 4.3 Redis

| 项目 | 值 |
|------|-----|
| 容器内地址 | `langfuse-redis:6379` |
| 密码 | `langfuse-redis-secret` |

### 4.4 安全密钥（NEXTAUTH / 加密）

| 密钥 | 值 |
|------|-----|
| `NEXTAUTH_SECRET` | `66959d0d214f0714ee0e064412e12583f2c9214ebbb384af7013c11c12633ce4` |
| `SALT` | `1fddb49ee65746c08a46d4f54e338254` |
| `ENCRYPTION_KEY` | `ea00e06b97639c2b4035e1dc0aa67911e6fb39cde2cf8242ee8a39582bee132e` |

---

## 五、业务接入指南

### 5.1 Python 应用（RAGFlow / FastAPI / Flask / Django）

#### 环境变量方式

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-ade6a02d-1393-4af4-9100-c755789722cc
LANGFUSE_SECRET_KEY=sk-lf-a4850c13-3608-470f-a19e-6ee5f16c625b
LANGFUSE_HOST=http://192.168.2.13:3030
```

#### 代码方式

```python
from langfuse import Langfuse

langfuse = Langfuse(
    public_key="pk-lf-ade6a02d-1393-4af4-9100-c755789722cc",
    secret_key="sk-lf-a4850c13-3608-470f-a19e-6ee5f16c625b",
    host="http://192.168.2.13:3030"
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

environment_variables:
  LANGFUSE_PUBLIC_KEY: "pk-lf-ade6a02d-1393-4af4-9100-c755789722cc"
  LANGFUSE_SECRET_KEY: "sk-lf-a4850c13-3608-470f-a19e-6ee5f16c625b"
  LANGFUSE_HOST: "http://192.168.2.13:3030"
```

### 5.2 RAGFlow 配置

RAGFlow v0.26.4 接入 Langfuse，直接使用以下环境变量：

```yaml
# ragflow 服务添加环境变量
environment:
  LANGFUSE_PUBLIC_KEY: "pk-lf-ade6a02d-1393-4af4-9100-c755789722cc"
  LANGFUSE_SECRET_KEY: "sk-lf-a4850c13-3608-470f-a19e-6ee5f16c625b"
  LANGFUSE_HOST: "http://192.168.2.13:3030"
```

或在代码中手动集成：

```python
from langfuse import Langfuse

langfuse = Langfuse(
    public_key="pk-lf-ade6a02d-1393-4af4-9100-c755789722cc",
    secret_key="sk-lf-a4850c13-3608-470f-a19e-6ee5f16c625b",
    host="http://192.168.2.13:3030"
)
```

### 5.3 Node.js / TypeScript 应用

```bash
npm install langfuse
```

```typescript
import { Langfuse } from "langfuse";

const langfuse = new Langfuse({
  publicKey: "pk-lf-ade6a02d-1393-4af4-9100-c755789722cc",
  secretKey: "sk-lf-a4850c13-3608-470f-a19e-6ee5f16c625b",
  baseUrl: "http://192.168.2.13:3030",
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

```python
from langfuse import Langfuse
l = Langfuse(public_key="pk-...", secret_key="sk-...", host="http://192.168.2.13:3030")
print(l.auth_check())  # 返回 True 表示连接成功
```

或用 curl：

```bash
curl -u "pk-lf-ade6a02d-1393-4af4-9100-c755789722cc:sk-lf-a4850c13-3608-470f-a19e-6ee5f16c625b" \
  http://192.168.2.13:3030/api/public/projects
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

# 队列积压检查（trace 收不到时的首要诊断）
docker exec langfuse-redis redis-cli -a langfuse-redis-secret \
  LLEN 'bull:otel-ingestion-queue:wait'
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
docker exec langfuse-redis redis-cli -a langfuse-redis-secret \
  LLEN 'bull:otel-ingestion-queue:wait'
# ClickHouse 空
docker exec langfuse-clickhouse clickhouse-client -q "SELECT count() FROM traces"
```

**修复**：
1. 修复 Docker 代理（systemd override: `/etc/systemd/system/docker.service.d/http-proxy.conf` → `HTTP_PROXY=http://192.168.2.70:7897`）
2. `docker pull langfuse/langfuse-worker:3`
3. 在 `docker-compose.yml` 添加 `langfuse-worker` 服务（与 Web 共享相同环境变量）
4. `docker compose up -d langfuse-worker`

**结果**：Worker 启动后自动消费积压队列，ClickHouse 在 30 秒内写入全部历史 trace。

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

1. **API 密钥安全**：Secret Key 不要提交到 Git，建议通过环境变量或密钥管理服务注入。
2. **PostgreSQL 持久化**：数据存储在 `postgres-data` Docker Volume 中，备份时注意备份该卷。
3. **网络**：Langfuse 使用外部网络 `docker_default`（`external: true`），新服务需要加入此网络才能用容器名通信。
4. **SALT 的重要性**：`SALT`（`1fddb49ee65746c08a46d4f54e338254`）用于生成 `fast_hashed_secret_key`，修改它会导致所有 API 密钥失效。
5. **密码初始化**：`LANGFUSE_INIT_USER_PASSWORD` 仅在首次启动时生效，数据库已有用户后不再自动更新。
