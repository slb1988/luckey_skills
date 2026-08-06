# RAGFlow 运行故障排障

常见运行时故障的根因、诊断和修复。

## 症状速查

| 症状 | 日志特征 | 根因 | 修复 |
|------|----------|------|------|
| 频繁被踢出登录 | `SECURITY WARNING: Using auto-generated SECRET_KEY` 多次出现 | Web worker 内部重启导致重新生成 SECRET_KEY，JWT 失效 | 设 `RAGFLOW_SECRET_KEY` 固定密钥 |
| 文档图片无法下载 | `SSRF guard blocked URL` / `non-public address` | 文档内图片 URL 指向内网 IP（如 MinIO 的 `192.168.2.13`），被 SSRF 拦截 | `ALLOW_ANY_HOST=1` |
| 文档 chunk 元数据写入失败 | `Limit of total fields [2000] has been exceeded` | ES 动态字段超限 | 调高 `total_fields.limit`（见 [ES 运维](elasticsearch-ops.md)） |
| MySQL 连接断开 | `Database connection issue` / `MySQL server has gone away` | 高负载下 MySQL 连接超时 | 通常是瞬时故障，RAGFlow 有重试机制；频繁出现则检查宿主机内存 |
| 文档卡在 RUNNING（假运行） | `0 tasks are ahead in the queue` 但长时间无进度；chunk=0 不变 | Redis 内存超限触发 `allkeys-lru` 驱逐，任务队列条目丢失 | 增大 Redis `--maxmemory`（见下方任务队列丢失章节） |

---

## SECRET_KEY 生命周期

### 存储机制

`common/settings.py` 中 SECRET_KEY 的确定流程：

```
模块导入时 init_secret_key()
  ├── 读环境变量 RAGFLOW_SECRET_KEY（≥32 字符）→ 直接返回
  ├── 读 service_conf.yaml ragflow.secret_key → 返回
  └── 无 → 返回 None（SECRET_KEY 全局变量 = None）

首次调用 get_secret_key() 时（SECRET_KEY is None）
  └── _get_or_create_secret_key()
        └── Redis DB 1 中 key ragflow:system:secret_key
             ├── 已存在 → 返回已有值
             └── 不存在 → 生成新 key → 写入 Redis → 打印 SECURITY WARNING
```

关键点：`_get_or_create_secret_key()` **不缓存到内存**，每次都查 Redis。但正常运行时 Redis key 存在，返回相同值，不触发 WARNING。

### "SECURITY WARNING" 出现的场景

该 WARNING 表示 Redis 中没有 `ragflow:system:secret_key`，于是生成了全新密钥。常见原因：

1. **首次启动**（正常）
2. **Redis 数据被清空**（DB 1 被 flush 或重启且无持久化）
3. **Web worker 内部重启** — RAGFlow 的 `ragflow_server.py` 使用 Quart（Python ASGI），在高负载或某些异常下 worker 会内部重启而不退出进程。重启时如果 Redis key 丢失则触发新 key 生成

### 修复：固定 SECRET_KEY

在 `.env` 中设置 `RAGFLOW_SECRET_KEY`（需 ≥32 字符），`init_secret_key()` 在模块导入时直接读取，跳过 Redis：

```bash
# 生成随机密钥
openssl rand -hex 32

# 添加到 .env
echo "RAGFLOW_SECRET_KEY=<生成的值>" >> .env
```

设置后 `get_secret_key()` 直接返回内存中的固定值，不再查询 Redis，**彻底消除 JWT 因 worker 重启而失效的问题**。

> `RAGFLOW_SECRET_KEY` 环境变量在代码中由 `init_secret_key()` 读取，但 `_get_or_create_secret_key()` 中的 env var 检查被注释掉了。因此该变量**只在模块首次导入时生效**；进程重启后可正常工作，仅内部 worker 重启无效（但此时它走 Redis 路径，只要 Redis key 还在就不会变）。

---

## SSRF Guard 拦截

### 机制

RAGFlow v0.26.4 的 `common/ssrf_guard.py` 对所有服务端发起的 HTTP 请求做 SSRF 防护：

- **检查范围**：文档图片下载（`rag/app/naive.py` 的 `download_images`）、REST API 连接器、RSS 源、OAuth 头像获取等
- **判断逻辑**：对目标 hostname 做 DNS 解析 → 检查解析出的 IP 是否 `ip.is_global`
- **被拦截的地址**：`127.0.0.1`、`10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16`、link-local、multicast 等

### 触发场景

从飞书等外部平台导入文档时，文档正文中的图片 URL 保留的是源地址。如果图片已同步到本地 MinIO（`192.168.2.13:9000`），SSRF guard 会因为内网 IP 拦截下载请求：

```
SSRF guard blocked URL: hostname='192.168.2.13' resolved to non-public address=192.168.2.13
Failed to download/open image from http://192.168.2.13:9000/...
```

### 修复：ALLOW_ANY_HOST

`.env` 中 `ALLOW_ANY_HOST=1` 控制 `ssrf_guard.py` 中 `_allow_any_host()` 返回值。设 1 后 `assert_url_is_safe()` 和 `assert_host_is_safe()` 直接跳过 `ip.is_global` 检查。

```bash
# .env
ALLOW_ANY_HOST=1
```

> `.env` 注释说此变量仅用于 "test_db_connection and allow private/local database hosts"，但代码实现中**作用于所有 SSRF 检查**（URL 和 host 级别均适用）。修改后需 `docker compose up -d ragflow-cpu` 重启生效。

---

## 任务队列丢失（文档假 RUNNING）

### 症状

一批文档卡在 RUNNING 状态，`chunk=0` 长时间不变，progress_msg 显示 `0 tasks are ahead in the queue`（排在队首却无人消费）。此外还有一种变体：子任务全部 `Task done`、chunk 已索引，但文档级状态永远不更新（停留在"解析中 X%"）。

### 根因：Redis maxmemory allkeys-lru 驱逐

RAGFlow 配置了 NATS 做消息队列（`service_conf.yaml` 中 `task_executor.message_queue_type: 'nats'`），但 NATS 容器只属于 `ragflow-go` profile 未启动。实际回退到 **Redis DB 1** 做任务队列。

`docker-compose-base.yml` 中 Redis 启动参数：

```yaml
command: ["redis-server", "--maxmemory", "128mb", "--maxmemory-policy", "allkeys-lru"]
```

- **128MB** 上限在大量文档并发解析时极易打满
- **`allkeys-lru`** 策略在内存满时无条件驱逐任意 key（包括任务队列条目），不区分 volatile/持久
- 队列条目从 Redis 消失 → executor 轮询不到任务 → MySQL 里文档永远是 RUNNING

### 诊断

```bash
# 检查 Redis 驱逐历史（> 0 即发生过驱逐）
docker exec docker-redis-1 redis-cli -a ${REDIS_PASSWORD} INFO stats | grep evicted_keys

# 检查内存峰值 vs 上限
docker exec docker-redis-1 redis-cli -a ${REDIS_PASSWORD} INFO memory | grep -E "used_memory_peak_human|maxmemory_human"

# 检查当前内存策略
docker exec docker-redis-1 redis-cli -a ${REDIS_PASSWORD} CONFIG GET maxmemory-policy
```

典型异常信号：`evicted_keys` 数万以上 + `used_memory_peak` > `maxmemory`。

### 修复

**1. 增大 Redis 内存上限**（治本）：

修改 `docker-compose-base.yml`：

```yaml
command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}",
  "--maxmemory", "512mb", "--maxmemory-policy", "allkeys-lru"]
```

然后重建 Redis 并重启 RAGFlow：

```bash
cd /data/ragflow/repo/docker
docker compose up -d redis
docker compose restart ragflow-cpu
```

**2. 恢复已卡住的文档**（治标）：

```python
# 批量停止 chunk=0 的假 RUNNING 文档，然后重新解析
# 子任务已完成但文档级状态未回写的（chunk > 0），只停不重启
```

**3. 永久方案：启用 NATS**（可选）：

在 `.env` 中把 `ragflow-go` 加入 `COMPOSE_PROFILES`，启动 NATS 专用消息队列，彻底不依赖 Redis 做任务调度。

### 为什么子任务全完成但文档状态不回写

大文档被切成多个 Page 子任务，子任务通过 Redis 队列分发和回写。**文档级完成状态回写也是一条 Redis 消息**。如果在回写那一刻 Redis 正好内存满触发驱逐，这条回写消息就丢了，文档永远停在中间状态。

症状区分：
- **chunk=0** → 队列条目全丢，从未被消费 → 停止后重新触发
- **chunk>0 但状态 RUNNING** → 子任务已完成，回写消息丢了 → **只停止，不重触发**（chunk 已索引，检索不受影响）
