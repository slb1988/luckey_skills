# Memory Center 运维

## 完整运维命令

```bash
cd /share/Container/memory_center/memory-center

# 状态（健康检查）
docker compose ps

# 启动 / 应用改动（自动 recreate 受影响容器）
docker compose up -d

# 停止 / 全量重启
docker compose down
docker compose restart graphiti   # 单服务重启
docker compose restart neo4j

# 日志
docker compose logs -f graphiti
docker compose logs -f neo4j
docker compose logs -f ollama

# 资源占用
docker stats memory-center-neo4j memory-center-graphiti memory-center-ollama
```

## 端口检查（部署前确认无占用）

```bash
for p in 8005 7474 7687 11434; do
  (exec 3<>/dev/tcp/127.0.0.1/$p) 2>/dev/null && echo "$p 已占用" || echo "$p 空闲"
done
```

> 端口占用时的改法：改 `compose.yml` 里 `ports` 的左侧宿主端口（如 `8006:8000`），Graphiti 与 Neo4j 之间的内部连接用容器名 `bolt://neo4j:7687` 不受影响。

## 直接查 Neo4j

```bash
# 统计各类节点数量
docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' \
  "MATCH (n) RETURN labels(n) AS labels, count(*) AS cnt;"

# 查实体
docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' \
  "MATCH (n:Entity) RETURN n.name, n.group_id;"

# 查关系（实体之间的边）
docker exec memory-center-neo4j cypher-shell -u neo4j -p '<密码>' \
  "MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity) RETURN a.name, type(r), r.name, b.name;"
```

> `<密码>` 从 `.env` 的 `NEO4J_PASSWORD` 取，不要在对话中回显。

## 备份与恢复

```bash
# 备份 Neo4j 数据库（写入 backup/ 目录）
docker exec memory-center-neo4j neo4j-admin database dump neo4j --to-path=/backup

# 恢复（先停止 neo4j，用空数据目录）
docker compose stop neo4j
docker exec memory-center-neo4j neo4j-admin database load neo4j --from-path=/backup --overwrite-destination=true
docker compose start neo4j
```

Ollama 模型已持久化在 `data/ollama/`，直接 `tar czf memory-center-backup.tar.gz <项目目录>` 即可整体备份。

## 从零重新部署（关键步骤）

1. 恢复目录结构 + `compose.yml` + `.env` + `patches/zep_graphiti.py` + `config/neo4j.conf`。
2. `NEO4J_USER=neo4j`，`NEO4J_PASSWORD` >= 8 位（管理员用户名必须是 neo4j）。
3. 检查端口（见上），有占用就改 compose 左侧宿主端口。
4. 拉镜像并启动：
   ```bash
   docker compose pull
   docker compose up -d
   ```
5. 首次需拉 Ollama 的 embedding 模型（已持久化在 `data/ollama/` 则跳过）：
   ```bash
   docker exec memory-center-ollama ollama pull bge-m3
   ```
6. 验证：
   ```bash
   docker compose ps                    # 三容器均 healthy
   curl -s http://127.0.0.1:8005/healthcheck   # {"status":"healthy"}
   ```
   写入一条消息后用 `/search` 检索（见 references/api.md），确认能抽取出实体并返回结果。
