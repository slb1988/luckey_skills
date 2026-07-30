# RAGFlow 模型接入

RAGFlow v0.26+ 将模型配置存在 MySQL 中（per-tenant）。Web UI 上的设置最终落库，修改后刷新页面即可生效。

## Provider 与 Base URL

| 能力 | Provider | Base URL | 备注 |
|---|---|---|---|
| LLM | OpenAI-API-Compatible | `http://host:8000/v1` | 兼容 OpenAI 对话接口 |
| Embedding | Ollama | `http://host:11434` | 不需要 `/api` 后缀 |
| Rerank | GPUStack / Xinference / TEI | `http://host:8002` | 需要 `/rerank` 端点 |

如果 RAGFlow 的 HuggingFace provider 不走本地，改用 GPUStack/Xinference。

## IP 变更批量修复

当模型服务器 IP 变化时，直接改 MySQL `tenant_model_instance.extra` 中的 `base_url`：

```sql
UPDATE tenant_model_instance
SET extra = JSON_REPLACE(extra, '$.base_url',
    REPLACE(JSON_UNQUOTE(JSON_EXTRACT(extra, '$.base_url')), '旧IP', '新IP'))
WHERE extra LIKE '%旧IP%';
```

无需重启 RAGFlow。更详细的 DB 操作见 `.claude/skills/ragflow-deploy/references/database-config.md`。

## 验证连通性

```bash
# OpenAI 兼容
curl -s --connect-timeout 3 http://host:8000/v1/models
# Ollama
curl -s --connect-timeout 3 http://host:11434/api/tags
```

## 常见错误

| 错误 | 原因 | 解决 |
|---|---|---|
| `Connection timeout to host` | base_url 地址/端口不可达或防火墙 | 检查网络、端口转发、防火墙 |
| `404 Not Found` | base_url 路径不对 | LLM 需要 `/v1`，Embedding 不需要 `/api` |
| `TEI compute cap ... not compatible` | TEI 镜像与 GPU 架构不匹配 | 改用 GPUStack/Xinference 或自建 Python rerank 服务 |
| Rerank 模型不存在 | Ollama 官方无 rerank 模型 | 自建 Docker rerank 服务 |

## 完整后端示例

一种可用的本地后端组合：

| 服务 | 端口 | 技术栈 | 模型 |
|---|---|---|---|
| LLM | 8000 | vLLM Docker | Qwen3-30B-A3B-Instruct (AWQ 4-bit) |
| Embedding | 11434 | Ollama | bge-m3 |
| Rerank | 8002 | Python HTTP + Transformers | BAAI/bge-reranker-v2-m3 |

更详细的部署步骤见 `D:\Github\ObsidianVault\luckey\000 InBox\RAGFlow+RAG完整部署手册.md`。
