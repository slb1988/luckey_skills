# RAGFlow 运行故障排障

常见运行时故障的根因、诊断和修复。

## 症状速查

| 症状 | 日志特征 | 根因 | 修复 |
|------|----------|------|------|
| 频繁被踢出登录 | `SECURITY WARNING: Using auto-generated SECRET_KEY` 多次出现 | Web worker 内部重启导致重新生成 SECRET_KEY，JWT 失效 | 设 `RAGFLOW_SECRET_KEY` 固定密钥 |
| 文档图片无法下载 | `SSRF guard blocked URL` / `non-public address` | 文档内图片 URL 指向内网 IP（如 MinIO 的 `192.168.2.13`），被 SSRF 拦截 | `ALLOW_ANY_HOST=1` |
| 文档 chunk 元数据写入失败 | `Limit of total fields [2000] has been exceeded` | ES 动态字段超限 | 调高 `total_fields.limit`（见 [ES 运维](elasticsearch-ops.md)） |
| MySQL 连接断开 | `Database connection issue` / `MySQL server has gone away` | 高负载下 MySQL 连接超时 | 通常是瞬时故障，RAGFlow 有重试机制；频繁出现则检查宿主机内存 |
| 文档状态长期停留在 RUNNING | 排队提示或分块数长期不变 | 数据库状态、队列派发和索引产物有独立生命周期 | 按下方[观测信号](#观测信号的边界)交叉判断 |
| binlog 写入量与解析工作量不成比例 | 进度和消息不变，计时字段仍更新 | SQL 更新列范围与 FULL binlog 行镜像范围不同 | 见下方[配置与行镜像](#parser_config-与行镜像) |

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

## 解析任务与持久化机制

适用范围：本部署的 RAGFlow v0.26.4 Python executor、Redis 队列及 Elasticsearch 索引路径。其他 executor 或消息后端应按实际运行实现确认，配置中的后端名称不等于运行时证据。

### 职责与完成路径

| 层 | 保存什么 | 与其他层的关系 |
|---|---|---|
| Redis DB 1 的 `te.<priority>.common` stream / consumer group | 任务消息、领取位置、未 ACK 的投递 | 管派发；消息或 key 的生命周期不会自动回滚 MySQL 的任务、文档状态 |
| MySQL `task` | 每个子任务的进度、消息、重试次数、已写入的 chunk IDs | 执行事实；一篇文档可拆为多个 Page 子任务，各自推进 |
| MySQL `document` | 文档级 `run`、`progress`、`progress_msg` 和统计信息 | 由子任务聚合出的视图，不是消费者存活记录 |
| Elasticsearch | 已索引的 chunk | 索引产物与文档级状态不是同一原子提交，部分 chunk 可先于整篇完成存在 |

`api/ragflow_server.py:update_progress` 每 6 秒进入 `DocumentService.update_progress()`，由 `_sync_progress()` 查询 MySQL 子任务并写回文档汇总；`update_progress_immediately(docs)` 也进入同一聚合函数。**文档完成状态由数据库聚合得出，不依赖一条专门的 Redis“完成回写消息”。**

候选文档由文档进度与子任务联查决定，混合成功/失败子任务的 `FAIL` 文档仍可参与聚合。上传确认、消息提交、解析完成、索引可用是不同阶段；客户端上传成功不能代替后三项的状态确认。

### 观测信号的边界

| 信号 | 实际含义 | 需要配合的证据 |
|---|---|---|
| `0 tasks are ahead in the queue` | 同优先级队列中排在该文档前面的任务数为零；计算会扣除文档自身的排队任务 | 自身任务是否已领取、是否有执行进展，不能由“前方为零”推断 |
| `XLEN` | stream 当前保留的消息总数，含已消费且未删除的历史消息 | 待领取积压看 group `lag`，不是直接拿长度当待办数 |
| group `lag` / `pending` | 分别表示未投递积压、已投递但未 ACK 的条目 | pending 不代表仍在执行，需结合所属 consumer 和 task 变化 |
| consumer `idle` / 存在性 | 消费者的交互活性或已登记身份 | 消费者在线不能证明某个历史任务消息仍在 stream 中 |
| stream 首 ID、`entries-added`、group 位置 | 当前 stream 实例及投递位置 | 区分同一队列的延续与 key 重新创建，不能只看相同 key 名 |
| `task.update_date`、`chunk_ids`、实际索引数量的增量 | 子任务或索引产物正在推进 | keyword/embedding/indexing 阶段的文档级进度可能较长时间不变 |
| `document.run` / `chunk_num` | 汇总状态和分块统计 | 零分块可处于正常生成阶段；非零也可能只是部分子任务完成 |
| `evicted_keys` / 内存峰值 | 当前 Redis 进程生命周期内的累计驱逐和峰值 | 时间窗增量与 stream 身份、任务记录用于定位具体队列事件 |

监控告警中的状态、耗时和增长阈值表达的是候选条件，不是派发记录或执行事实本身。任务活性应跨队列、子任务和索引三层判断。

### 状态聚合契约

| 契约 | 设计含义 |
|---|---|
| 以 ID 定位当前状态 | 定时扫描与即时入口共用逻辑，传入字典不是权威的最新状态；当前 `run/progress/progress_msg/process_begin_at` 从 DB 窄读即可，不需要完整 `parser_config` |
| 主解析与特殊任务进度分离 | 已完成主解析的文档可继续执行 GraphRAG/RAPTOR/Mindmap；这类任务未结束时，既有 `progress=1` 可保留，不必降为子任务百分比 |
| 取消判断覆盖写入时刻 | 查询之后仍可能发生取消；UPDATE 的 WHERE 条件保留 CANCEL 排除，保证聚合写入不会覆盖新取消状态 |
| 业务变化决定持久化 | 比较状态、进度和消息（考虑浮点存储精度），没有变化时不必写入；duration 随真实变化更新，而不是充当独立持久心跳 |

### parser_config 与行镜像

`parser_config` 不只是用户配置，也承载表格派生 schema：

| 内容 | 来源与用途 |
|---|---|
| 解析参数、模型与分块设置 | 用户或数据集配置；控制解析行为 |
| `field_map` | `rag/app/table.py` 将存储列名与原始列名映射合并至 KB 配置，用于表格检索/SQL；不是普通元数据抽取开关的同义字段 |
| `table_column_names` | 同一解析器汇集表格列名并写入 KB 配置 |
| 新文档继承的 KB 配置 | 派生 schema 可随配置一起进入多个 document 行，因此影响不限于最初那张表 |

`enable_metadata=false` 不表示上述表格派生 schema 不存在。派生映射与既有索引有语义关联，配置大小不能直接等同于可删除缓存。

SQL 的 `SET` 列表、SELECT 投影与 binlog 行镜像是三个不同范围。即使只更新 `process_duration/update_time`，MySQL `binlog_row_image=FULL` 仍记录整行的前后镜像，大 `parser_config` 也在其中：

```text
更新事件频率 × 文档行大小 × 前后镜像 ≈ binlog 写入规模
```

窄 SELECT 减少读取与反序列化；无业务变化时跳过 UPDATE 才消除相应写事件。修改行镜像策略属于 MySQL 复制/CDC 契约，不只是 RAGFlow 内部开关。

### Redis 与容器配置配对

| 配置层 | 对应保证 | 与另一层的配对关系 |
|---|---|---|
| `maxmemory` + `maxmemory-policy` | 容量与运行时驱逐语义 | 队列 stream 即使 TTL=-1 也属于 `allkeys-lru` 的驱逐范围；`noeviction` 保留已有 key，容量不足时写请求会被拒绝，仍需容量规划与显式提交结果 |
| `appendonly yes` + `appendfsync everysec` | 持久日志及 fsync 节奏 | 与运行时驱逐保护独立；everysec 不等于零丢失窗口，持久化也不重建已丢失消息 |
| AOF 文件 + 持久卷 + 启动参数 | 容器替换后加载已有队列数据 | 相同卷中有 AOF 与新进程实际启用 AOF 必须同时成立；stream 标识与 group 位置表达恢复结果 |
| `CONFIG SET` + `CONFIG GET` | 当前 Redis 进程的有效配置 | 不会重写 Docker 容器的创建参数 |
| Compose `command` + 容器 `Config.Cmd` | 期望启动配置与已创建容器的实际启动配置 | `docker restart` 复用旧 Cmd；编辑 Compose 后需让容器按新规格创建，才能在后续启动中继承新参数 |
| RAGFlow 宿主源码 + 只读 bind + Python 模块加载 | 代码来源、容器可见文件、正在执行的版本 | 修改 repo 不会自动修改镜像代码；bind 让文件可见，运行进程仍需加载对应版本，文件 hash 与进程启动信息各证明一层 |

任务队列的一组配置配对示例（容量需按实际工作负载选择）：

```yaml
command: ["redis-server", "--requirepass", "${REDIS_PASSWORD}",
  "--maxmemory", "2gb", "--maxmemory-policy", "noeviction",
  "--appendonly", "yes", "--appendfsync", "everysec"]
```
