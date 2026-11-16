---
name: build-api-proxy
description: build-api-proxy（内网 LLM API 中转网关）运维参考。虚拟 key 转发到 Kimi(moonshot)/DeepSeek 上游，Anthropic 兼容协议，Docker 部署于本机 8600 端口。当用户提到 build-api-proxy、LLM 网关、虚拟 key、history.db、relay.db、request_history、LLM 用量/余额查询、8600 端口、团队 token 统计、请求留档、留档清理/HISTORY_RETENTION 时触发；提到模型请求总是失败/断流/写一半停/stream_interrupted/idle_timeout/upstream_error/连不上上游/网关出网或代理配置时同样触发。即使用户只说"网关挂了"、"Kimi 老是失败"、"回答说到一半断了"、"查一下谁的 token 用得多"、"history.db 太大了"、"看看 LLM 请求记录"、"模型 id 不通/模型目录里有没有某模型"也应触发。
---

# build-api-proxy 运维参考

pyAutomation 集成共性知识：[pyauto-shared](../pyauto-shared/SKILL.md)。网关是外部依赖；先核实际主机，“本机部署”不适用于任意会话。优先请求元数据，正文仅在必要且获准时读取并脱敏。

## 是什么

团队自建的**内网 LLM API 中转网关**：给成员发虚拟 key，转发到 Kimi(moonshot, kimi-k3)/DeepSeek 等 Anthropic 兼容上游。Node.js 应用（`node src/server.js`），Docker 单容器部署在本机。

- pyautomation 后端的 `/user/get_llm_balance/<user>` 接口查询的就是它（余额数据经 `balance-push-cache.json` 推送）
- 所有经网关的 LLM 请求**完整留档**（含请求/响应原文），用于排障与用量分析

<memory category="troubleshooting">
客户端请求里的 model id 必须命中网关**真实可路由的上游 id**，网关目录/display 名 ≠ 可路由 id。Kimi k3.1 实测（2026-10）：可路由 id 是 `k3.1-pro`（curl 直连验证 thinking 正常），目录里的 `kimi-k3.1-pro` 反而路由不通；另有高速档 `k3.1-pro-highspeed` 上游实测可用。给新客户端配模型时先用 curl 直连网关验证 id，不要照抄目录名。
</memory>

## 部署形态

| 项 | 值 |
|----|-----|
| 容器 | `build-api-proxy`（restart: 自动拉起，healthy） |
| 端口 | `8600->8600` |
| 镜像 | 本地构建 `build-api-proxy:latest`；**每次发布打一个 `rollback-YYYYMMDD` tag 备份**（已有 30+ 个，每个仅增量几百 KB，不要清理） |
| 数据卷 | `relay-data` → `/app/data`（宿主机 `/var/lib/docker/volumes/relay-data/_data`，root 权限，日常操作用 `docker exec` 进容器看） |
| 挂载 | `/data/pipe-staging` → `/app/pipe-staging`（**只读挂载**，HISTORY_PURGE_WATERMARK 实际写不进去） |
| 主进程 | `node src/server.js`，WorkDir `/app` |
| 启动方式 | **手工 `docker run`**（无 compose 标签，`docker-compose.yml` 不是线上真源）。2026-11-04 起标准入口：`/home/dev/.config/build-api-proxy/start.sh` + `runtime.env`（600，含 ADMIN_TOKEN/ENCRYPTION_KEY + 代理三件套） |
| 出网 | Kimi/moonshot 经局域网代理 `192.168.2.70:7897`（韩国出口）；deepseek 与内网直连（见下节） |

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

## 出网（2026-11-04：容器**不走任何代理**）

当前 `runtime.env` 不含任何 PROXY 变量，容器出口 = 宿主公网 IP `180.165.60.40`（上海电信）。`api.deepseek.com` / `api.kimi.com` / 内网均直连。

**为什么曾经挂过代理**：2026-11-04 实测宿主→`api.kimi.com`（103.143.17.156，火山引擎高防）链路劣化，直连流式基本不可用（详见下节）。当时临时用 `HTTPS_PROXY=192.168.2.70:7897`（韩国出口）绕行，owner 决定「容器整体不走代理、不接受韩国出口」后已撤销。

- 代理版本 env 留在 `/home/dev/.config/build-api-proxy/runtime.proxy.env`，需要临时兜底时：`cp runtime.proxy.env runtime.env && ./start.sh`。
- 若日后重新启用，`NO_PROXY` 必须保留 `api.deepseek.com` 与内网段，否则 deepseek 与 `192.168.2.13:5000` 余额推送会被带到国外。

## 排障：stream_interrupted / idle_timeout 爆发（2026-11-04 实例，可照抄流程）

**症状**：`status='error'` + `http_status=200` + `error_type='stream_interrupted'`（或 `idle_timeout`）单日暴涨，散落在**全部**上游 Key（不是某把 key 坏）且跨 provider；用户侧表现是答案写到一半断流。当日实测：平时 2–3 次/天 → 389 次/天，429 次请求失败、13 人受影响。

**五步定位**（无需抓包，全部只读）：

1. 按天×error_type 看趋势，确认是「今天突变」还是长期背景噪音：
   ```bash
   docker exec build-api-proxy python3 -c "import sqlite3;c=sqlite3.connect('/app/data/history.db');[print(r) for r in c.execute('''SELECT substr(ts,1,10) d, SUM(error_type='stream_interrupted'), SUM(error_type='idle_timeout'), SUM(error_type='upstream_unreachable') FROM request_history WHERE ts>=date('now','-10 days') GROUP BY d ORDER BY d''')]"
   ```
2. 看 `upstream_label` / `key_name` 分布：**全 Key 均匀 = 路径级故障**；集中在 1–2 把 = 那把 key 的问题。
3. 看 `response_body` 尾部：以半截 `content_block_delta` 结尾 + 合成 `event: error … Upstream stream interrupted` = 上游 socket 被打断（真实原因码只在 `e.cause.code`，**网关目前不记**，见下）。
4. 宿主机/容器网络对照：`ping`（ICMP 通不代表 TCP 通）、`curl -sv --resolve` 反复建连（本例：TCP:443 15/15 通但夹 1–2s SYN 重传，HTTPS 20 次里 6 次握手后 0 字节超时）。**注意别只看流式**：直连时连 60-token 的非流式请求也会 90s 超时，说明不是大包/PMTU 问题。
5. **直连 vs 代理对照实验**（决定性，证明是否出在本机出网）：容器内解密一把上游 key 后跑同题长流。脚本要点：`require('/app/src/services/crypto.js').decrypt(api_key_encrypted, process.env.ENCRYPTION_KEY)`；moonshot 认证头是 `authorization: Bearer <key>`（**不是 x-api-key**），base 取 `key_templates.base_url`（如 `https://api.kimi.com/coding`，不是 providers.js 里的默认）。本例：直连 3/3 失败（rc=56 / 300s 超时），经代理 3/3 完整成功。

**本次结论**：上海电信 180.165.60.40 → 103.143.17.156（火山引擎高防 volcddos）路径丢包/重置，非网关代码问题。旁证：同宿主 deepseek（61.170.x）直连 2/2 完美、4s；`api.kimi.com` 全 DNS（223.5.5.5/119.29.29.29/114/8.8.8.8）都只返回单一 A 记录，无备用节点可切。

**验证手法（改完必做）**：
- 出口归属：容器内 `fetch('https://myip.ipip.net')` 应显示代理出口（韩国）。
- 冒烟：`node scripts/smoke.mjs --base http://127.0.0.1:8600 --admin-token $ADMIN_TOKEN`（`--live` 那一项走 `/v1/responses`，本就长期 FAIL，别误判为本次改动引起）。
- 端到端长流：临时建 key → `POST /v1/messages` stream 连发 6 次，检查 `message_stop` 存在且无 `"type":"error"` → 撤销临时 key。

**坑位**：
- 重建容器后启动要 **~2.5 分钟**（`history.db` 585GB 启动扫盘），期间 healthcheck 连续失败显示 `unhealthy`，扫完自动转 `healthy`，不是故障。
- 容器是手工 `docker run` 起的，env 改动必须重建容器；下次重建务必用 `start.sh`/`runtime.env`，否则代理三件套会丢、故障复现。
- 回滚：保留旧容器 `build-api-proxy-old-*`，`docker rename` 回去即可。

## 常用运维命令

```bash
docker logs -f build-api-proxy              # 日志
docker restart build-api-proxy              # 重启（配置变更后）
docker ps --filter name=build-api-proxy     # 状态（应显示 healthy）
curl -s localhost:8600/                     # 探活
```

## 其他已知问题（2026-11-04 盘点）

- `chatgpt` provider **一把 key 都没有**（relay.db 只有 53 moonshot + 1 deepseek），但 `/v1/models` 仍宣传 gpt-* 九档 → 调用直接 `503 no_upstream_available`（实测有人单日重试 33 次）。要么上 key，要么把 gpt-* 从目录摘掉。
- `history.db` 实占 ~302G（apparent 585G），freelist ≈ 400GB 空闲页，启动日志提示 `needs one-off VACUUM`；`VACUUM INTO` 需等量空闲空间。
- `HISTORY_RETENTION_DAYS` 线上实际是 **7**（skill 旧文写 30）；蒸馏只有 7 天正文可蒸。
- 日志里高频 `BadRequestError: request aborted` + `ECONNABORTED` = 客户端上传 body 半路断开，不入库、只污染日志。

## 关联服务与排障线索

- 本机共 3 个 MySQL：`mysql`:13306（pyautomation 主库）、`mysql3`:14306、`docker-mysql-1`:14307（ragflow）——2026-09-08 磁盘写满事故中三者曾集体"假活"（docker ps 显示 Up 实际 exited），修复手法=删容器+清残留网络端点+原数据卷重建
- 磁盘看门狗 `/data/scripts/server_watchdog.sh`（cron 每 10 分钟）监控磁盘水位与 ragflow binlog 洪水，告警发飞书管理群
- 磁盘大头参考：本服务 history.db、ragflow binlog、opencode 容器内日志、`/data/minio`（未经确认不要动）

<memory category="troubleshooting">
- 网关模型目录（/v1/models）列出的 id **不等于上游真实可用 id**，接入新模型必须发真实请求验证，不能照抄目录。2026-10 实测：目录里的 `kimi-k3.1-pro` 上游路由不通（报 `recognized as other`），Kimi 3.1 真实可用 id 是 `k3.1-pro` / `k3.1`，另有高速档 `k3.1-pro-highspeed`（均 Anthropic 协议，已验证）。给 pi/Claude Code 等客户端配新模型时先用 curl 打一次真实 chat 请求确认 id 再写配置。
</memory>
