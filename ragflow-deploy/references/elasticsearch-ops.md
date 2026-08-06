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

> **实际观察**：在某些部署中，索引后缀对应的是文档的 `created_by`（租户/用户 ID），而不是 URL 里的 `dataset_id`。这意味着同一租户下的多个知识库可能共享同一个 `ragflow_*` chunk 索引。

## 为什么字段会爆

RAGFlow 的 `table` chunk 模式会把表格列名映射成 ES 字段。不同文档、不同 sheet 的列名各不相同，全部累积到同一个 `ragflow_*` 索引的 mapping 里：

```
 ragflow_675273...
   └── properties
       ├── 菜谱名
       ├── 主菜要求
       ├── 2025-05-12 00:00:00_tks
       ├── 食用效果
       ├── ... (每个新列都加一个字段)
```

ES 默认 `index.mapping.total_fields.limit = 1000`，累积到上限后任何带新列的 chunk 都写不进去。

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

ES 8.x 自带默认 **1000**，RAGFlow 部署时通过 `ragflow_total_fields` 索引模板预设为 **2000**。当导入大量不同结构的文档（如飞书 wiki、Excel 表格）时，动态字段数可能超过 2000，写入报错：

```
Limit of total fields [2000] has been exceeded while adding new fields [2]
```

表现为文档解析成功但 chunk 元数据无法写入 ES（`Failed to insert metadata` 日志）。

### 修改已有索引

```bash
curl -s -u elastic:infini_rag_flow -X PUT 'localhost:1200/<index>/_settings' \
  -H 'Content-Type: application/json' \
  -d '{"index.mapping.total_fields.limit": 5000}'
```

### 更新模板（未来索引自动生效）

```bash
curl -s -u elastic:infini_rag_flow -X PUT 'localhost:1200/_index_template/ragflow_total_fields' \
  -H 'Content-Type: application/json' \
  -d '{
    "index_patterns": ["ragflow_*"],
    "template": {
      "settings": {
        "index.mapping.total_fields.limit": 5000
      }
    },
    "priority": 100
  }'
```

模板匹配所有 `ragflow_*` 模式的新索引，**已存在的索引不受模板影响**，需单独 `_settings` 更新。

## 治本：关闭动态映射

提高 `total_fields.limit` 只是扩容。如果表格列名持续多样化，迟早再次打满。

更彻底的方案是让 ES 不再把新列自动展开成 mapping 字段：

```bash
# 对已有索引关闭动态映射
curl -s -u elastic:infini_rag_flow -X PUT 'localhost:1200/<index>/_mapping' \
  -H 'Content-Type: application/json' \
  -d '{"dynamic": false}'

# 创建模板，新索引自动继承
curl -s -u elastic:infini_rag_flow -X PUT 'localhost:1200/_index_template/ragflow_disable_dynamic' \
  -H 'Content-Type: application/json' \
  -d '{
    "index_patterns": ["ragflow_*", "memory_*", "ragflow_doc_meta_*"],
    "priority": 500,
    "template": {
      "mappings": {
        "dynamic": false
      }
    }
  }'
```

`dynamic: false` 的效果：
- 新字段不再进入 mapping，不计入 `total_fields`
- 字段仍然作为原始 JSON 保存在 `_source` 中
- RAGFlow 的向量检索和文本检索依赖的核心字段（`content`, `content_ltks`, `q_1024_vec` 等）已经在 mapping 中定义，不受影响
- 表格列名作为 metadata 仍能被 RAGFlow 在召回后读取，只是不再被 ES 单独索引/聚合

## 验证

```bash
# 检查已有索引
curl -s -u elastic:infini_rag_flow 'localhost:1200/<index>/_settings?include_defaults=false'

# 检查索引 dynamic 设置
curl -s -u elastic:infini_rag_flow 'localhost:1200/<index>/_mapping' | python3 -c \
  "import sys,json; m=json.load(sys.stdin); print(list(m.values())[0]['mappings'].get('dynamic'))"

# 检查模板
curl -s -u elastic:infini_rag_flow 'localhost:1200/_index_template/ragflow_total_fields'
curl -s -u elastic:infini_rag_flow 'localhost:1200/_index_template/ragflow_disable_dynamic'
```

## 设计说明

- **ES 必须带认证**：8.x 默认 `xpack.security.enabled: true`，无认证的 curl 返回 401。
- **索引命名存在两种形态**：文档说按 `kb_id` 创建，但实际部署中可能按租户/用户 ID（`created_by`）创建。同一租户下的多个知识库共享同一个 `ragflow_*` 索引，字段会在租户维度累积。
- **表格列名即字段**：`table` chunk 模式把每个列名写入 ES mapping。跨文档、跨 sheet 的列名多样性是 `total_fields` 超限的根本原因。
- **动态映射是治本**：`dynamic: false` 阻止新列进入 mapping，同时保留 `_source`，不影响 RAGFlow 的核心向量/文本检索。
- **模板优先级**：`priority` 设得足够高（如 500），确保不被其他模板覆盖（ES 默认模板 priority 为 0）。
