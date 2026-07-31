# RAGFlow Elasticsearch 运维

RAGFlow 使用 Elasticsearch 8.x 作为向量数据库（DOC_ENGINE=elasticsearch）。容器端口 `9200`，宿主机映射 `1200`。

## 连接信息

| 项目 | 值 |
|------|-----|
| 宿主机地址 | `localhost:1200` |
| 容器内地址 | `elasticsearch:9200`（同 Docker 网络） |
| 用户 | `elastic` |
| 密码 | `.env` 中 `ELASTIC_PASSWORD`（当前为 `infini_rag_flow`） |
| 安全认证 | ES 8.x 默认开启；所有 REST API 需 `-u elastic:<password>` |

## 索引命名规则

RAGFlow 按知识库（kb）创建索引，模式为 `ragflow_*`：

| 索引模式 | 内容 | 示例 |
|----------|------|------|
| `ragflow_<kb_id>` | 主 chunk 索引，文档切分后的实际检索数据 | `ragflow_675273e67c7c11f18aba1bd33d775907` |
| `ragflow_doc_meta_<kb_id>` | 文档元数据 | `ragflow_doc_meta_675273e67c7c11f18aba1bd33d775907` |

`kb_id` 对应 RAGFlow 中知识库的唯一标识。

## 常用命令

```bash
# 查看所有索引
curl -s -u elastic:infini_rag_flow 'localhost:1200/_cat/indices?v'

# 查看指定索引的 settings
curl -s -u elastic:infini_rag_flow 'localhost:1200/<index>/_settings?include_defaults=false'

# 查看索引 mapping 字段数
curl -s -u elastic:infini_rag_flow 'localhost:1200/<index>/_mapping' | python3 -c \
  "import sys,json; m=json.load(sys.stdin); print(sum(1 for _ in str(m).split('\"type\"'))-1)"
```

## index.mapping.total_fields.limit

### 问题

ES 每个索引有字段数保护上限，默认 **1000**。当写入的 chunk 动态字段超过此值时，写入失败：

```
Limit of total fields [1000] has been exceeded while adding new fields [3]
```

RAGFlow 随着文档增多、字段类型多样化，容易触发此限制。

### 修改已有索引

```bash
curl -s -u elastic:infini_rag_flow -X PUT 'localhost:1200/<index>/_settings' \
  -H 'Content-Type: application/json' \
  -d '{"index.mapping.total_fields.limit": 2000}'
```

### 创建模板（未来索引自动生效）

```bash
curl -s -u elastic:infini_rag_flow -X PUT 'localhost:1200/_index_template/ragflow_total_fields' \
  -H 'Content-Type: application/json' \
  -d '{
    "index_patterns": ["ragflow_*"],
    "template": {
      "settings": {
        "index.mapping.total_fields.limit": 2000
      }
    },
    "priority": 100
  }'
```

模板匹配所有 `ragflow_*` 模式的新索引，已存在的索引不受模板影响，需单独更新。

### 验证

```bash
# 检查已有索引
curl -s -u elastic:infini_rag_flow 'localhost:1200/<index>/_settings?include_defaults=false'

# 检查模板
curl -s -u elastic:infini_rag_flow 'localhost:1200/_index_template/ragflow_total_fields'
```

## 设计说明

- **ES 必须带认证**：8.x 默认 `xpack.security.enabled: true`，无认证的 curl 返回 401。
- **索引按 kb_id 创建**：每个知识库独立索引，因此修改限额时需覆盖已有索引（`_settings`）+ 未来索引（`_index_template`）两处。
- **模板优先级**：设 `priority: 100` 确保不被其他模板覆盖（ES 默认模板 priority 为 0）。
