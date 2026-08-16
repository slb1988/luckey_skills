# Memory Center 运维

## 完整运维命令

```bash
cd /share/Container/memory_center/memory-center

# 状态（健康检查）
docker compose ps

# 启动 / 应用 compose 改动（自动 recreate 受影响容器）
docker compose up -d

# 停止 / 重启
docker compose down
docker compose restart graphiti   # 改补丁/.env 后必须 restart（不是 up -d）
docker compose restart neo4j

# 日志
docker compose logs -f graphiti
docker compose logs -f neo4j

# Ollama（备选 embedding，当前已停用）
docker compose stop ollama         # 停用
docker compose start ollama        # 恢复

# 资源占用
docker stats memory-center-neo4j memory-center-graphiti
```

## 端口检查（部署前确认无占用）

```bash
for p in 8005 7474 7687 11434; do
  (exec 3<>/dev/tcp/127.0.0.1/$p) 2>/dev/null && echo "$p 已占用" || echo "$p 空闲"
done
```

> 端口占用时的改法：改 `compose.yml` 里 `ports` 的左侧宿主端口（如 `8006:8000`）。Graphiti 与 Neo4j 之间走容器内网 `bolt://neo4j:7687`，不受宿主端口影响。

## 直接查 Neo4j

```bash
# 统计各类节点数量
docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' \
  "MATCH (n) RETURN labels(n) AS labels, count(*) AS cnt;"

# 查实体（含摘要）
docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' \
  "MATCH (n:Entity) RETURN n.name, n.summary, n.group_id;"

# 查关系
docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' \
  "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) RETURN a.name, r.name, b.name, r.fact;"

# 查原始输入（Episodic.content，模型无关，可作重嵌入种子）
docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' \
  "MATCH (e:Episodic) RETURN e.group_id, e.content, toString(e.valid_at);"
```

> `<密码>` 从 `.env` 的 `NEO4J_PASSWORD` 取，不要在对话中回显。

## 备份与恢复

⚠️ **Neo4j Community 版不支持在线 dump**（报 `The database is in use. Stop database and try again`）。在线备份是 Enterprise 功能，所以备份必须停库。

### 方式 A：离线 dump（逻辑备份，可恢复到新库）

```bash
docker compose stop neo4j
docker compose run --rm neo4j neo4j-admin database dump neo4j --to-path=/backup
docker compose start neo4j
```

### 方式 B：tar 数据目录（整目录快照，最简单）

```bash
docker compose stop neo4j
tar -czf backup/neo4j-$(date +%F).tar.gz data/neo4j
docker compose start neo4j
```

### 方式 C：在线导出原始文本（零停机，最小「重嵌入种子」）

```bash
docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' --format plain \
  "MATCH (e:Episodic) RETURN e.group_id, e.name, e.content, toString(e.valid_at);"
```

### 恢复

```bash
docker compose stop neo4j
docker compose run --rm neo4j neo4j-admin database load neo4j --from-path=/backup --overwrite-destination=true
docker compose start neo4j
```

> 备份/迁移策略详见 [reembedding.md](reembedding.md)。

## 从零重新部署（关键步骤）

1. 恢复目录结构 + `compose.yml` + `.env` + `patches/zep_graphiti.py` + `config/neo4j.conf`。
2. `.env` 配两把 key（`OPENAI_*` = CodePlan，`EMBEDDING_*` = 百炼 DashScope）；`NEO4J_USER=neo4j`，密码 >= 8 位。
3. 检查端口（见上），有占用就改 compose 左侧宿主端口。
4. 拉镜像并启动：
   ```bash
   docker compose pull
   docker compose up -d
   ```
5. 若要用本地 embedding（备选），启动 Ollama 并拉模型：
   ```bash
   docker compose start ollama
   docker exec memory-center-ollama ollama pull bge-m3   # 已持久化则跳过
   ```
   然后把 `.env` 的 `EMBEDDING_*` 指回 Ollama，`docker compose restart graphiti`。
6. 验证：
   ```bash
   docker compose ps                        # neo4j + graphiti healthy
   curl -s http://127.0.0.1:8005/healthcheck   # {"status":"healthy"}
   ```
   写入一条消息后用 `/search` 检索（见 [api.md](api.md)），确认能抽出实体并返回结果。
