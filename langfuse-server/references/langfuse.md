# Langfuse — LLM 可观测性平台

> 自部署于 `dev@auto-server`，Docker Compose 管理  
> 版本：Langfuse v3.174.1  
> 状态：✅ 运行中（2026-07-24 修复后）

---

## 一、架构概览

```
┌──────────────────────────────────────────────────────┐
│                   Langfuse Web UI                     │
│              http://192.168.2.13:3030                 │
└──────────────┬───────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────┐
│  langfuse (Next.js)        langfuse/langfuse:3       │
│  ┌─────────────────────────────────────────────────┐ │
│  │  内部依赖（同一 docker_default 网络）             │ │
│  │  • postgres  → langfuse-postgres:5432 (元数据)   │ │
│  │  • clickhouse → langfuse-clickhouse:8123 (分析)  │ │
│  │  • redis     → langfuse-redis:6379 (缓存/队列)   │ │
│  │  • minio     → langfuse-minio:9000 (事件/媒体)   │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

| 容器 | 镜像 | 端口 (宿主机) | 健康状况 |
|------|------|--------------|----------|
| `langfuse` | `langfuse/langfuse:3` | `3030:3000` | Up |
| `langfuse-postgres` | `postgres:15-alpine` | — (内部) | healthy |
| `langfuse-clickhouse` | `clickhouse/clickhouse-server` | — (内部) | healthy |
| `langfuse-redis` | `redis:7` | — (内部) | healthy |
| `langfuse-minio` | `minio/minio` | `9092:9000`, `9093:9001` | healthy |

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

| 场景 | Host 配置 | 说明 |
|------|----------|------|
| 容器内访问（统一推荐） | `http://192.168.2.13:3030` | 所有容器通用 |
| 同网络容器（也可用） | `http://langfuse:3000` | 需在同一 docker network |
| 宿主机本地 | `http://localhost:3030` | 宿主机直接访问 |
| 局域网其他机器 | `http://192.168.2.13:3030` | 外部机器访问 |

**修复内容**：
- 在 NAT PREROUTING 添加了 `-i br-+` 的 DNAT 规则，使 Docker bridge 流量也能命中端口转发
- 在 NAT POSTROUTING 添加了 MASQUERADE 规则，确保回包正确路由
- 规则已保存至 `/etc/iptables/rules.v4`，重启后通过 systemd 服务恢复

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
# 查看状态
cd /mnt/disk2/langfuse && docker compose ps

# 查看日志
docker compose -f /mnt/disk2/langfuse/docker-compose.yml logs -f

# 重启全部服务
cd /mnt/disk2/langfuse && docker compose restart

# 重建并启动
cd /mnt/disk2/langfuse && docker compose up -d

# 停止
cd /mnt/disk2/langfuse && docker compose down

# 进入 PostgreSQL
docker exec -it langfuse-postgres psql -U postgres -d langfuse

# 配置文件位置
# docker-compose.yml: /mnt/disk2/langfuse/docker-compose.yml
# 管理面板 HTML: /mnt/disk2/langfuse/index.html
```

---

## 七、故障记录

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
