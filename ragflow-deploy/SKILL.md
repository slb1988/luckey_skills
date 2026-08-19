---
name: ragflow-deploy
description: |
  RAGFlow 部署与运维助手——在 Ubuntu 服务器上安装、配置、排障 RAGFlow（开源 RAG 知识库平台）。
  触发场景：(1) 用户提到部署/安装 RAGFlow、RAG Flow、ragflow；(2) 用户需要搭建知识库、RAG 平台、
  文档问答系统；(3) 用户在已有多服务的服务器上安装新软件需要避端口冲突；(4) RAGFlow 容器启动失败、
  镜像拉取失败、Docker Hub 限流等排障；(5) 模型配置修改——IP 变更后更新 API 地址、修改模型密钥等
  运维操作。即使用户只是说"帮我装个 RAGFlow"或"知识库怎么搭"也应该触发。
  国内网络环境下的 Docker 镜像拉取问题（mirror 选择、代理配置、docker.elastic.co 等替代源）是本 skill
  的核心覆盖范围。
---

# RAGFlow Deploy

在 Ubuntu 服务器上部署 RAGFlow v0.26.4，处理端口冲突、Docker Hub 限流、镜像源选择等实际问题。

## 适用场景

- 全新安装 RAGFlow 到已有多个 Docker 服务的 Ubuntu 服务器
- 端口冲突（nginx:80、已有 mysql/redis/minio 等）
- Docker Hub 镜像拉取困难（国内网络环境）
- 复用已有 MinIO 实例

## 工作流程

当用户要求安装/部署 RAGFlow 时，按以下步骤执行。

### 前置：判断任务类型

- **部署/安装** → Step 1 部署文档
- **配置修改**（IP 变更、改 API 地址、改密钥、新团队模型复制、共享模型等）→ 读 [数据库与配置说明](references/database-config.md)
- **ES 运维**（字段超限、索引管理、模板设置、安全认证等）→ 读 [Elasticsearch 运维参考](references/elasticsearch-ops.md)
- **SSRF 拦截、JWT 失效、Worker 频繁重启、任务队列丢失（文档假 RUNNING）等运行故障** → 读 [排障参考](references/troubleshooting.md)
- **排障** → Step 1 + 查日志

### Step 1：读取详细部署文档

```
references/ubuntu-server-setup.md
```

该文档包含完整的部署流程、每一步的具体命令、端口冲突处理方案、镜像拉取策略、踩坑记录和修复方案。

**关键点**（决策前先读文档）：
- **端口规划**：先 `ss -tlnp` + `docker ps` 摸清现有服务，再改 `.env`
- **镜像拉取顺序**：mysql/valkey → 轩辕 mirror → ES → docker.elastic.co → ragflow 最后
- **向量数据库选择**：默认用 elasticsearch（infinity 在国内 mirror 有拉取问题）
- **MinIO 复用**：如果宿主机已有 minio，停掉 RAGFlow 自带的，改用 `host.docker.internal`

### Step 2：按文档执行部署

对照 `references/ubuntu-server-setup.md` 逐步操作，特别注意：

1. **不要直接用 `docker compose up -d` 一步到位**——大镜像拉取会超时
2. **先逐个拉镜像**，再 compose up
3. **镜像拉取策略**：
   - `library/*` 类（mysql、valkey）→ `docker.xuanyuan.me` mirror
   - `elasticsearch` → `docker.elastic.co`（不走 Docker Hub）
   - 第三方镜像（ragflow、minio）→ Docker Hub 直连（走 daemon proxy）
4. **耐心**：ragflow 镜像 1.2GB，代理速度约 1MB/s，需约 20 分钟

### Step 3：验证启动

```bash
docker logs docker-ragflow-cpu-1 | grep "ready"
curl -sI http://localhost:9386
```

看到 `RAGFlow server is ready` + HTTP 200 即成功。

### Step 4：告知用户

启动成功后告知用户：
- 访问地址（Web UI 端口）
- 首次需要注册账号（无预设管理员）
- 已映射的所有端口号

## 关键设计决策

| 场景 | 决策 | 原因 |
|------|------|------|
| 向量数据库 | elasticsearch | infinity 镜像在国内拉取失败 |
| MinIO | 复用宿主机已有实例 | 避免维护两套 MinIO |
| RAGFlow 镜像源 | Docker Hub 原生 tag | 阿里云/华为云 registry 未同步 |
| ES 镜像源 | docker.elastic.co | Docker Hub 已下架 ES 官方镜像 |
| Langfuse 连接方式 | 容器名直连 `http://langfuse:3000` | RAGFlow 和 Langfuse 在同一 `docker_default` 网络，走 Docker 内部 DNS 避免 iptables NAT 依赖 |

## Langfuse 配置

RAGFlow v0.26.4 内置了 Langfuse tracing，密钥存储在 MySQL `tenant_langfuse` 表中（通过 Web UI 的 API 设置），**不是**仅靠环境变量生效。`dialog_service.py` 通过 `TenantLangfuseService.filter_by_tenant()` 读取。

### Host 选择

| 场景 | Host | 端口 |
|------|------|------|
| 同 Docker 网络 | `http://langfuse:3000` | 容器内部端口 |
| 外部 IP | `http://192.168.2.13:3030` | 宿主机映射端口（需 iptables） |

**推荐用容器名直连**：省去 iptables NAT 规则依赖，`docker compose` 重启后容器 IP 变化也不会断。

### 网络连通前提

RAGFlow 和 Langfuse 必须在**同一个 Docker 网络**才能用容器名互访。默认 RAGFlow 在 `docker_ragflow`，Langfuse 在 `docker_default`，不互通。

```bash
# 一次性修复（持久化到容器重启，但不 survive docker compose down）
docker network connect docker_default docker-ragflow-cpu-1

# 永久修复：在 RAGFlow docker-compose.yml 的 ragflow-cpu service 添加
networks:
  - ragflow
  - default   # docker_default 的外部网络
```

> 如果使用外部 IP (`192.168.2.13:3030`)，需确认 Docker 网桥到宿主机的 iptables 规则放行该端口。常见症状：`httpcore.ConnectError: Name or service not known`。

### 已知代码 bug（v0.26.4）

`langfuse_api.py` 的 `get_api_key()` 函数存在变量遮蔽（variable shadowing）bug：

```python
# Line 70: 局部变量 langfuse 遮蔽了 langfuse 模块
langfuse = Langfuse(...)
# Line 74: 报 AttributeError——Python 在局部变量上找 .api.core
# 而非模块
```

**症状**：`AttributeError: 'LangfuseAPI' object has no attribute 'core'`

**修复**：在文件头部导入 `ApiError`，except 子句直接用类名：

```python
from langfuse.api.core.api_error import ApiError  # 新增
# ...
except ApiError as api_err:  # 替换原 langfuse.api.core.api_error.ApiError
```
