---
name: memory-center
description: Memory Center（Graphiti 时序知识图谱记忆服务）运维与部署指南。记录 QNAP NAS 上 memory-center 的三容器架构（Neo4j + Graphiti + Ollama/bge-m3）、端口、DeepSeek 兼容性补丁、Neo4j 用户名坑位、运维命令与 REST API 用法。当用户提到 memory-center、graphiti、记忆中心、记忆图谱、记忆服务、Neo4j 记忆，或需要查看状态/重启/备份/排障/重新部署/写入或检索记忆时触发。即使用户只说"memory-center 怎么了""帮我看下记忆服务""记忆图谱挂了"也应触发。
---

# Memory Center (Graphiti 记忆中心)

基于 [Graphiti](https://github.com/getzep/graphiti) 的时序知识图谱记忆服务，运行在 QNAP NAS 的 Docker 中。为 AI agent 提供可查询的长期记忆（实体/关系抽取 + 向量检索 + 时序追踪）。

## 快速信息

| 项目 | 值 |
|------|-----|
| 项目目录 | `/share/Container/memory_center/memory-center/` |
| 编排文件 | `compose.yml` |
| 环境配置 | `.env`（含 DeepSeek key、Neo4j 密码） |
| 兼容补丁 | `patches/zep_graphiti.py` |
| 项目 README | `README.md`（详细文档，优先参考） |

## 架构（3 个容器）

| 服务 | 容器名 | 镜像 | 端口 | 说明 |
|------|--------|------|------|------|
| Neo4j | `memory-center-neo4j` | `neo4j:5.26-community` | 7474 (HTTP) / 7687 (Bolt) | 图数据库 |
| Graphiti | `memory-center-graphiti` | `zepai/graphiti:latest` | **8005** → 8000 | REST API + Swagger |
| Ollama | `memory-center-ollama` | `ollama/ollama:latest` | 11434 | 本地 embedding (bge-m3) |

数据流：Graphiti 调 DeepSeek（LLM 抽取）→ 调 Ollama（bge-m3 生成 1024 维向量）→ 写入 Neo4j。

## 关键坑位

- **Neo4j 管理员用户名必须是 `neo4j`**。`NEO4J_AUTH` 只允许设置密码，写成别的用户名会启动失败：`Invalid admin username, it must be neo4j.`
- **改 Neo4j 密码后要清空 `data/neo4j/`**：数据用旧密码加密，改密码后旧数据无法登录，需删除数据目录重建。
- **DeepSeek 模型名**用 `.env` 的 `MODEL_NAME` 控制：`deepseek-v4-flash`（快）/ `deepseek-v4-pro`（强）。
- **Ollama 在 CPU 上慢**：NAS 是 J4125（4 核）/ 8GB 内存，bge-m3 首次加载 + 每次 embedding 约 1~2 秒，首次写入/检索偏慢属正常。
- **`latest` 标签实为 graphiti-core 0.22.0**：`zepai/graphiti` 只有 `latest` 和 `0.22.0` 两个可用标签，Docker Hub 未跟进 GitHub 的 0.29.x 版本，升级需谨慎。

## 常用命令速查

```bash
cd /share/Container/memory_center/memory-center
docker compose ps                    # 状态（三容器是否 healthy）
docker compose up -d                 # 启动 / 应用改动（自动 recreate）
docker compose restart graphiti      # 重启单服务
docker compose logs -f graphiti      # 看日志
docker compose down                  # 全量停止
```

## 参考文件

| 文件 | 何时读 |
|------|--------|
| [references/architecture.md](references/architecture.md) | 了解目录结构、数据流、DeepSeek 兼容性补丁；排障或重新部署前 |
| [references/operations.md](references/operations.md) | 完整运维命令、端口检查、直查 Neo4j、备份、从零重新部署 |
| [references/api.md](references/api.md) | 调用 REST API 写入 / 检索记忆 |

## 注意事项

- `.env` 含真实密钥（DeepSeek key、Neo4j 密码），不要在对话中回显完整内容。
- 父目录 `/share/Container/memory_center/` 下旧的 `compose.yml`/`.env` 是历史草稿（含无效用户名 slb1988），正式配置在 `memory-center/` 子目录内。
