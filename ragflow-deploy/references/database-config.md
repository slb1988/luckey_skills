# RAGFlow 数据库与配置说明

## 数据库概览

RAGFlow 运行配置（模型提供商、API 地址、密钥等）存储在 MySQL `rag_flow` 库中，不是配置文件。Web UI 上配置的所有内容最终落库。

| 服务 | 容器名 | 端口 | 密码 |
|------|--------|------|------|
| MySQL | `docker-mysql-1` | 内网 `docker-mysql-1:3306` | `infini_rag_flow` |
| Elasticsearch | `docker-es01-1` | 9200 | `infini_rag_flow` |
| Valkey/Redis | `docker-redis-1` | 6379 | `infini_rag_flow` |

## 模型配置相关表

### `tenant_model_provider` — 模型提供商

每个 Provider 一条记录，如 OpenAI-API-Compatible、Ollama、GPUStack、Xinference、DeepSeek 等。

```sql
-- 查看所有提供商
SELECT id, provider_name, tenant_id FROM tenant_model_provider;
```

### `tenant_model_instance` — 模型实例（核心）

每个模型实例（如 `qwen3-30b`、`bge-m3`）一条记录。**关键字段 `extra`** 是 JSON，存储 `base_url`、`region` 等连接参数。

```sql
-- 查看所有模型实例
SELECT tmi.id, tmi.instance_name, tmp.provider_name, tmi.extra
FROM tenant_model_instance tmi
JOIN tenant_model_provider tmp ON tmi.provider_id = tmp.id;
```

`extra` 列结构：

```json
{"base_url": "http://192.168.2.76:8000/v1", "region": "default"}
```

- `base_url` — 模型服务的 API 地址（含端口和路径，如 `/v1`）
- `region` — 固定为 `"default"`

### `tenant_llm` — 租户级 LLM 配置

包含 `api_base`、`api_key`、`llm_factory`、`model_type` 等字段。如果模型是通过系统内置 Provider 添加的，相关连接信息可能在这里。

## 常见运维操作

### IP 变更：批量更新模型地址

当模型服务器 IP 变化时，所有通过「OpenAI-API-Compatible / Ollama / GPUStack / Xinference」添加的内网模型都需要更新 `base_url`。

```sql
-- 查看当前含有旧 IP 的记录
SELECT tmi.id, tmi.instance_name, tmp.provider_name, tmi.extra
FROM tenant_model_instance tmi
JOIN tenant_model_provider tmp ON tmi.provider_id = tmp.id
WHERE tmi.extra LIKE '%旧IP%';

-- 批量替换 IP（JSON_REPLACE + REPLACE 组合）
UPDATE tenant_model_instance
SET extra = JSON_REPLACE(extra, '$.base_url',
    REPLACE(JSON_UNQUOTE(JSON_EXTRACT(extra, '$.base_url')), '旧IP', '新IP'))
WHERE extra LIKE '%旧IP%';
```

**无需重启** — RAGFlow 每次请求时实时读取数据库，修改后刷新页面即可生效。

### 验证模型连通性

```bash
# 直接 curl 测试 API 端点
curl -s --connect-timeout 3 http://192.168.2.76:8000/v1/models  # OpenAI 兼容接口
curl -s --connect-timeout 3 http://192.168.2.76:11434/api/tags  # Ollama
```

### 日志排查

```bash
# RAGFlow 日志挂在宿主机
tail -f /data/ragflow/repo/docker/ragflow-logs/ragflow_server.log
```

常见错误关键字：`Connection timeout to host`、`Client error '404 Not Found'`（base_url 路径不对或端口不对）。

## 模型多租户架构

模型配置是 **per-tenant（按团队隔离）** 的。每个团队有独立的三层模型数据链：

```
tenant_model_provider (provider_name, tenant_id)
    └── tenant_model_instance (instance_name, api_key, extra, provider_id)
        └── tenant_model (model_name, model_type, provider_id, instance_id)
```

`tenant_id` 只在 provider 层出现，instance 和 model 通过 `provider_id` 间接归属。

**没有内置全局模型共享**。`service_conf.yaml` 中的 `user_default_llm` 在 v0.26.4 中未被代码消费（Admin 日志报 `Unknown configuration key`）。因此新注册的团队不会自动获得任何模型配置。

### 跨团队复制模型

将已配置好的源团队模型批量复制到其他所有团队：

```bash
# 执行脚本（幂等：已有 provider 的团队会自动跳过）
docker exec -i docker-mysql-1 mysql -uroot -pinfini_rag_flow rag_flow \
  < /data/ragflow/copy_models_to_all_tenants.sql
```

脚本逻辑：遍历所有目标团队，对每个团队复制 provider → instance → model 三级数据，所有 ID 用 `UUID()` 重新生成，API key 和 base_url 保持不变（所有团队共享同一套后端模型服务）。

### 查看各团队模型配置状态

```sql
SELECT t.name, COUNT(tmp.id) as provider_count
FROM tenant t
LEFT JOIN tenant_model_provider tmp ON tmp.tenant_id = t.id
GROUP BY t.id, t.name;
```

## 数据库备份

```bash
docker exec docker-mysql-1 mysqldump -uroot -pinfini_rag_flow rag_flow \
  > /data/backups/ragflow_$(date +%Y%m%d).sql
```
