---
name: langfuse-server
description: Langfuse LLM 可观测性平台运维。自部署于本机 Docker，提供 tracing、prompt management、evaluation 等功能。当用户提到 langfuse、可观测性、tracing、LLM 监控、langfuse 配置、langfuse 密钥、langfuse 连不上、langfuse 超时、langfuse host 配置时触发。即使用户只说"langfuse 怎么配"或"tracing 连不上"也应触发。
---

# Langfuse Server

本机 Docker 自部署的 Langfuse LLM 可观测性平台运维指南。

## 触发后立即读取

当此 skill 触发时，先读取完整的参考文档：

```
references/langfuse.md
```

该文档包含：
- 架构概览（6 个容器：langfuse、langfuse-worker、postgres、clickhouse、redis、minio）
- 连接信息（Web UI 地址、管理员账号和凭据变量名）
- API 密钥的环境变量配置（不存储实际值）
- 内部组件配置（数据库、缓存、对象存储）
- 业务接入指南（Python / Node.js / RAGFlow / LiteLLM / 容器内访问）
- 运维命令（启停、日志、队列诊断、状态检查）
- 故障记录与修复

## 本地凭据

实际 API 密钥、管理员/组件密码和安全密钥只放本 skill 目录的 `.env`（Git 忽略），无值模板为 `.env.example`。其他机器需单独配置，不通过 Git 分发实际值。

只向用户说明变量名和文件位置，不回显值。Agent 查询用 env-read-guard 的 `keys`；需要凭据时，用 `pipe KEY -- <静默下游命令>`，从本 skill 目录执行，以定位这里的 `.env`。没有 guard 时由应用自己的配置加载器注入，不直接读取或打印密钥文件。

## 常见场景

### 用户问"langfuse 密钥是什么"
→ 说明 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` 存在本地 `.env`；接入方法见参考文档第三节，不把实际值放进回复。

### 用户问"XXX 容器连不上 langfuse"
→ 确认防火墙规则已修复（`/etc/iptables/rules.v4`），指导用户使用 `http://192.168.2.13:3030`。
如果不行，检查容器是否在 `docker_default` 网络内。

### 用户问"怎么在 RAGFlow 里配置 langfuse"
→ 将本地凭据注入服务的 `LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY` 和 `LANGFUSE_HOST` 环境变量。Docker Compose 用 `.env` 插值并只映射这三项；不要把含运维密码的整个文件注入业务容器。具体配置见参考文档第五节。

### 用户问"langfuse 挂了"或"trace 收不到"
→ 执行 `cd /mnt/disk2/langfuse && docker compose ps` 检查所有 6 个容器状态。
先查 Worker 是否运行（`langfuse-worker`），再查队列是否积压（Redis `LLEN bull:otel-ingestion-queue:wait`）。
详见 references/langfuse.md 第七节「诊断 trace 收不到」。

### 用户问"langfuse 内部错误"/Dashboard 报 500
→ 先看 Web 日志 `docker logs langfuse --tail 50` 确认具体报错。
常见原因：镜像版本过旧，与新版 ClickHouse 不兼容（日志显示 `scores.all` + ClickHouse `Not found column`）。
→ 拉取最新镜像重建：`docker pull langfuse/langfuse:3 langfuse/langfuse-worker:3 && docker compose up -d langfuse langfuse-worker`
→ 详见 references/langfuse.md 第七节「ClickHouse 版本漂移」。

### 用户问"怎么创建新 API 密钥"
→ 通过 Web UI：登录 → Project Settings → API Keys → Create。
或通过数据库直插（需要 bcrypt hash，详见 references/langfuse.md）。

## 关键文件

| 文件 | 路径 |
|------|------|
| docker-compose | `/mnt/disk2/langfuse/docker-compose.yml` |
| Docker 代理配置 | `/etc/systemd/system/docker.service.d/http-proxy.conf` |
| 代理地址 | `http://192.168.2.70:7897` |
| 管理面板 HTML | `/mnt/disk2/langfuse/index.html` |
| iptables 持久化 | `/etc/iptables/rules.v4` |
| 参考文档 | `references/langfuse.md` |
| 本地凭据 / 无值模板 | `.env`（忽略） / `.env.example` |
