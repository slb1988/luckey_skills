# Re-embedding：换 Embedding 模型后的数据迁移

## 核心事实：原始文本已经存在 Neo4j 里

Graphiti 默认 `store_raw_episode_content=True`，把**模型无关的原始文本**全部落库：

| 位置 | 内容 | 是否随 embedding 模型变化 |
|------|------|:---:|
| `Episodic.content` | 原始输入全文 | 否 |
| `Entity.name` / `.summary` | 实体名 / 摘要 | 否 |
| `EntityEdge.fact` | 关系事实 | 否 |
| `Entity.name_embedding` / `EntityEdge.fact_embedding` | 向量 | **是** |

结论：换 embedding 模型 = **只重算向量**。图结构、实体、关系、原始文本全部保留，**无需重灌原始输入**。

## 为什么必须 re-embedding

不同模型的向量空间不同，cosine 相似度跨模型比较无意义。旧向量 + 新向量混用会导致：

- 节点去重失效（相同实体被判成不同实体）
- 检索召回错乱（相似度分数无意义）

所以**换模型后必须让全图向量来自同一个模型**。

## 迁移流程

1. **备份**（见下）
2. 改 `.env` 的 `EMBEDDING_*` → 新模型
3. `docker compose restart graphiti`
4. **重新 embedding 存量数据**（方式 A 或 B）
5. 验证：`POST /search` 检索旧记忆，确认能召回

## 重新 embedding 的两种方式

### 方式 A：re-embed 脚本（推荐，只重算向量）

读 Neo4j 存量的 `Entity.name` / `EntityEdge.fact` → 调新 embedding API → 把新向量写回对应字段。

- 图结构不动，LLM 不重跑，成本最低。
- 向量索引按字段自动更新，写回即可。

### 方式 B：清空重灌（简单，代价大）

1. `POST /clear` 清空全图。
2. 把备份导出的原始输入重新喂 `/messages`。

- 简单可靠，但重跑 LLM 抽取（耗时 + 花钱），且抽取结果可能略有差异。

## 备份策略

Neo4j Community 版**不支持在线 dump**（报 `The database is in use. Stop database and try again`），在线备份是 Enterprise 功能。

| 方式 | 停库 | 命令 | 用途 |
|------|:---:|------|------|
| 离线 dump | 是 | 见下 | 完整逻辑备份，可恢复到新库 |
| tar 数据目录 | 是 | 见下 | 整目录快照，最简单 |
| 在线导出原始文本 | 否 | cypher-shell | 最小「重嵌入种子」，零停机 |

```bash
# 离线 dump（停库 → dump → 启动）
docker compose stop neo4j
docker compose run --rm neo4j neo4j-admin database dump neo4j --to-path=/backup
docker compose start neo4j

# tar 整目录快照
docker compose stop neo4j
tar -czf backup/neo4j-$(date +%F).tar.gz data/neo4j
docker compose start neo4j

# 在线导出原始文本（零停机，作为 re-embed 种子）
docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' --format plain \
  "MATCH (e:Episodic) RETURN e.group_id, e.name, e.content, toString(e.valid_at);"
```

## 建议

- **无需单独备份 input** —— 原始输入已在 `Episodic.content`。定期备份 Neo4j 本身即可（一次备份 = input + 图结构 + 向量全包）。
- 换 embedding 模型**前**务必先 dump 一份，再 re-embed。
- 迁移窗口内服务仍可读（旧向量还能检索），但建议一次性完成 re-embed，避免新旧向量长期混用。
