---
name: ragflow-deploy
description: |
  RAGFlow 部署与运维助手——在 Ubuntu 服务器上安装、配置、排障 RAGFlow（开源 RAG 知识库平台）。
  触发场景：(1) 用户提到部署/安装 RAGFlow、RAG Flow、ragflow；(2) 用户需要搭建知识库、RAG 平台、
  文档问答系统；(3) 用户在已有多服务的服务器上安装新软件需要避端口冲突；(4) RAGFlow 容器启动失败、
  镜像拉取失败、Docker Hub 限流等排障。即使用户只是说"帮我装个 RAGFlow"或"知识库怎么搭"也应该触发。
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
