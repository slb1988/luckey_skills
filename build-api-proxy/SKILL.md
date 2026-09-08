---
name: build-api-proxy
description: build-api-proxy（内网 LLM API 中转网关）运维参考。虚拟 key 转发到 Kimi(moonshot)/DeepSeek 上游，Anthropic 兼容协议，Docker 部署于本机 8600 端口。当用户提到 build-api-proxy、LLM 网关、虚拟 key、history.db、relay.db、request_history、LLM 用量/余额查询、8600 端口、团队 token 统计、请求留档、留档清理/HISTORY_RETENTION 时触发。即使用户只说"网关挂了"、"查一下谁的 token 用得多"、"history.db 太大了"、"看看 LLM 请求记录"也应触发。
---

# build-api-proxy 运维参考

## 是什么

团队自建的**内网 LLM API 中转网关**：给成员发虚拟 key，转发到 Kimi(moonshot, kimi-k3)/DeepSeek 等 Anthropic 兼容上游。Node.js 应用（`node src/server.js`），Docker 单容器部署在本机。

- pyautomation 后端的 `/user/get_llm_balance/<user>` 接口查询的就是它（余额数据经 `balance-push-cache.json` 推送）
- 所有经网关的 LLM 请求**完整留档**（含请求/响应原文），用于排障与用量分析

## 部署形态

| 项 | 值 |
|----|-----|
| 容器 | `build-api-proxy`（restart: 自动拉起，healthy） |
| 端口 | `8600->8600` |
| 镜像 | 本地构建 `build-api-proxy:latest`；**每次发布打一个 `rollback-YYYYMMDD` tag 备份**（已有 30+ 个，每个仅增量几百 KB，不要清理） |
| 数据卷 | `relay-data` → `/app/data`（宿主机 `/var/lib/docker/volumes/relay-data/_data`，root 权限，日常操作用 `docker exec` 进容器看） |
| 挂载 | `/data/pipe-staging` → `/app/pipe-staging`（含 HISTORY_PURGE_WATERMARK） |
| 主进程 | `node src/server.js`，WorkDir `/app` |

## 数据文件（/app/data/）

| 文件 | 大小级别 | 内容 | 重要性 |
|------|---------|------|--------|
| `relay.db` | ~130M | **主库**：虚拟 key、上游 key、配额 | 🔴 核心数据，丢失=网关瘫痪 |
| `history.db` | **持续增长（见下）** | 请求留档库 | 🟡 可清理正文 |
| `history.db-wal/-shm` | MB 级 | SQLite WAL | 随库 |
| `balance-push-cache.json` | KB | 余额推送缓存 | ⚪ |

## history.db 请求留档（关键资产）

单表 `request_history`，每行 = 一次 LLM 请求的**完整留档**：

```
request_id, ts, virtual_key_id, key_name, key_prefix,
upstream_key_id, upstream_label, provider, model_requested, model_upstream,
stream, status, http_status, latency_ms, input_tokens, output_tokens,
error_type, request_body, response_body   ← 正文全文（占 99% 体积）
```

⚠️ **隐私敏感**：含全团队所有 LLM 对话明文（代码、提问、可能粘贴过的密钥）。任何能 `docker exec` 进本机的人都能读，对外分享前注意。

### 常用查询（容器内 python3，宿主无 sqlite3 客户端）

```bash
# 每人今日用量
docker exec build-api-proxy python3 -c "
import sqlite3
c = sqlite3.connect('/app/data/history.db')
for r in c.execute('''SELECT key_name, COUNT(*), SUM(input_tokens)/1e6, SUM(output_tokens)/1e6
                      FROM request_history WHERE ts > date('now')
                      GROUP BY key_name ORDER BY 3 DESC'''):
    print(r)"

# 查某次请求完整对话原文
docker exec build-api-proxy python3 -c "
import sqlite3
c = sqlite3.connect('/app/data/history.db')
r = c.execute(\"SELECT request_body, response_body FROM request_history WHERE key_name='某人' ORDER BY ts DESC LIMIT 1\").fetchone()
print(r[0][:2000])"
```

时间字段是 `ts`（ISO 字符串，UTC），**不是** created_at。

## 留档保留策略（体积治理）

配置经环境变量（`src/config.js`）：

| 变量 | 当前值 | 说明 |
|------|--------|------|
| `HISTORY_PURGE_ENABLED` | `true` ✅ | 总开关，默认关，开了才自动清理 |
| `HISTORY_RETENTION_DAYS` | 未设置 = **默认 30 天** | 超期记录删正文、**保留元数据行**（token/耗时/模型仍在，账单分析不受影响） |
| `HISTORY_PURGE_WATERMARK_PATH` | `/app/pipe-staging/watermark.txt` | 清理水位文件 |

**2026-09 实测**：~12.7GB/天增长，30 天稳态 ≈ 380G（曾占满磁盘的三大元凶之一）。改保留期只需改 env 重启容器，清理服务会自动删旧正文。删正文后要回收空间需 VACUUM（大库 VACUUM 需要等量空闲磁盘，或用 `VACUUM INTO` 到新文件再替换）。

## 常用运维命令

```bash
docker logs -f build-api-proxy              # 日志
docker restart build-api-proxy              # 重启（配置变更后）
docker ps --filter name=build-api-proxy     # 状态（应显示 healthy）
curl -s localhost:8600/                     # 探活
```

## 关联服务与排障线索

- 本机共 3 个 MySQL：`mysql`:13306（pyautomation 主库）、`mysql3`:14306、`docker-mysql-1`:14307（ragflow）——2026-09-08 磁盘写满事故中三者曾集体"假活"（docker ps 显示 Up 实际 exited），修复手法=删容器+清残留网络端点+原数据卷重建
- 磁盘看门狗 `/data/scripts/server_watchdog.sh`（cron 每 10 分钟）监控磁盘水位与 ragflow binlog 洪水，告警发飞书管理群
- 磁盘大头参考：本服务 history.db、ragflow binlog、opencode 容器内日志、`/data/minio`（未经确认不要动）
