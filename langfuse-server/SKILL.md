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
- 连接信息（Web UI 地址、管理员账号密码）
- API 密钥（pk-lf-... / sk-lf-...）
- 内部组件配置（数据库、缓存、对象存储）
- 业务接入指南（Python / Node.js / RAGFlow / LiteLLM / 容器内访问）
- 运维命令（启停、日志、队列诊断、状态检查）
- 故障记录与修复

## 常见场景

### 用户问"langfuse 密钥是什么"
→ 读取 `references/langfuse.md`，找到「三、API 密钥」部分。

### 用户问"XXX 容器连不上 langfuse"
→ 确认防火墙规则已修复（`/etc/iptables/rules.v4`），指导用户使用 `http://192.168.2.13:3030`。
如果不行，检查容器是否在 `docker_default` 网络内。

### 用户问"怎么在 RAGFlow 里配置 langfuse"
→ 给出环境变量：
```
LANGFUSE_PUBLIC_KEY=pk-lf-ade6a02d-1393-4af4-9100-c755789722cc
LANGFUSE_SECRET_KEY=sk-lf-a4850c13-3608-470f-a19e-6ee5f16c625b
LANGFUSE_HOST=http://192.168.2.13:3030
```

### 用户问"langfuse 挂了"或"trace 收不到"
→ 执行 `cd /mnt/disk2/langfuse && docker compose ps` 检查所有 6 个容器状态。
先查 Worker 是否运行（`langfuse-worker`），再查队列是否积压（Redis `LLEN bull:otel-ingestion-queue:wait`）。
详见 references/langfuse.md 第七节「诊断 trace 收不到」。

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
