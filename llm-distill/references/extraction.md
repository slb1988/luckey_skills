# extraction.md — 数据层细节与提取原理

## history.db 表结构

单表 `request_history`，每行 = 一次经网关的 LLM 请求完整留档：

```
request_id, ts, virtual_key_id, key_name, key_prefix,
upstream_key_id, upstream_label, provider, model_requested, model_upstream,
stream, status, http_status, latency_ms, input_tokens, output_tokens,
error_type, request_body, response_body
```

- `ts`：ISO 字符串 UTC（**不是** created_at）。按天过滤用 `WHERE ts LIKE '2026-08-12%'`。
- `key_name`：虚拟 key 归属人（`owner`、`zhuweijie`、`sunlaibing`…，另有 `verify-live`、`cost-probe-tmp` 等系统 key）。
- `request_body`：Anthropic messages API 格式 JSON（`model/system/messages/tools/metadata`），**含完整对话历史**——所以同一 session 的多次请求高度重复，必须去重。
- `response_body`：SSE 流格式（`event:message_start` / `data:{...}`），提取正文要解 SSE，一般不需要——**最长请求快照里 assistant 消息已全在 messages 里**。

## 正文保留与"空壳日期"

- `HISTORY_PURGE_ENABLED=true`，`HISTORY_RETENTION_DAYS` 未设 = 默认 30 天。超期记录删 `request_body`/`response_body` 但保留行（token/耗时仍可查账）。
- 2026-09 实测 ~12.7GB/天。一天正文总量约 4-5GB。
- 边界日会**部分被清**（如 2026-08-12：8841/14242 空壳，上午被清下午完整）——蒸馏时注明覆盖偏差。

### 关键 SQL（容器内 python3，宿主机无 sqlite3 客户端）

```python
import sqlite3
c = sqlite3.connect('/app/data/history.db')

# 全库范围与每日请求数
c.execute('SELECT MIN(ts), MAX(ts), COUNT(*) FROM request_history')
c.execute("SELECT substr(ts,1,10) d, COUNT(*) FROM request_history GROUP BY d ORDER BY d")

# 某天正文完整率（轻量，只算长度不读内容）
c.execute("""SELECT COUNT(*),
  SUM(CASE WHEN LENGTH(COALESCE(request_body,''))>10 THEN 0 ELSE 1 END)
  FROM request_history WHERE ts LIKE '2026-08-12%'""")

# 某天每人用量
c.execute("""SELECT key_name, COUNT(*), SUM(input_tokens)/1e6, SUM(output_tokens)/1e6
  FROM request_history WHERE ts LIKE '2026-08-12%' GROUP BY key_name ORDER BY 3 DESC""")
```

### ⚠️ 已知坑：容器内重查询 OOM

在整表上做 `GROUP BY` 且触碰大文本列（如逐行判 `request_body` 非空）会被 OOM Kill（exit 137）。对策：**按天拆小查询**、只用 `LENGTH()` 不取内容、需要内容时流式逐行取（`for row in c.execute(...)` 不要 fetchall）。

## session 去重原理

`request_body.metadata.user_id` 是 JSON 字符串，内含 `session_id`（Claude Code / Codex / Pi 的会话 ID）：

```json
{"user_id": "{\"device_id\":\"...\",\"account_uuid\":\"\",\"session_id\":\"6cc4a1c2-...\"}"}
```

去重键 = `(key_name, session_id)`，**保留 messages 数最多的那次请求**——它就是该 session 最完整的 transcript（含全部 user/assistant/tool_result）。无 session_id 时退化为 request_id。一天约几千请求 → 去重后几百个 session。

## 关键词过滤（可选，默认关闭）

**默认全量提取不过滤**（蒸馏目标是每人全量工作记录，关键词会漏非 UE 内容）。第二参数传逗号分隔关键词才启用过滤，仅用于定向主题（如只蒸 UE 相关、或只蒸 pyauto 平台）。

```
unreal, uproject, uplugin, .uasset, unrealbuildtool, uobject, uclass, uproperty,
ufunction, aactor, blueprint, 蓝图, angelscript, gameplayability, worldpartition,
world partition, commandlet, nanite, lumen, .build.cs, target.cs, lyra, ue5, ue4,
maindev, gameplaytag, gameplay tag, editorutility, slate, umg, pak , cook, 烘焙,
材质, shader
```

调优说明：

- 对**原始 body 小写后**做子串匹配，宁宽勿漏（一天匹配率 ~95% 很正常，因为团队工作主要就是这个 UE 项目）。
- 已知噪声词：`cook`（可能匹配烹饪语境，实际很少）、`pak `（带空格防误伤）。如果蒸非 UE 主题，替换关键词列表即可（如 pyauto 平台类：`pyauto`,`flask`,`teamcity` 等）。
- 太宽的词不要加（`actor` 会误伤 actor 模型；`perforce` 全员都用）。

## transcript 文件格式（distill_extract.py 产物）

每会话一个 `<key>_<request_id前13位>_<首问hash12位>.txt`，内容按消息序：

```
===== user =====
<用户文本 或 [tool_result] 截断2000字 或 [tool_use 名称] 参数截断400字>

===== assistant =====
<助手文本 + [thinking] 思维链（每块截 1500 字）>
```

约 3/4 的请求带 thinking 块（Anthropic 扩展思考），提取脚本以 `[thinking]` 前缀保留——思维链是「🧠 思维链精选」的素材源。

## 机器人流量识别（话题索引阶段直接跳过）

团队成员里混着大量自动化管线流量，特征明显：

| 特征开头 | 是什么 |
|---|---|
| `You are the Skill extraction sub-agent.` | skill 自动抽取子代理 |
| `You are deciding whether a new conversation turn continues...` | plan-mode 判定 |
| `Generate a short kebab-case slug` | plan-mode slug 生成 |
| `reply with exactly: ok` | 探活 |
| `[SUGGESTION MODE: Suggest what the user might naturally type next...` | 输入建议 |
| `Project context: Registered command prefixes:` | 机器人系统提示 |
| `verify-live` / `cost-probe-tmp` key | 系统 key |
| `This is an automatically generated checkpoint...` / `The conversation history before this point was compacted...` | harness 上下文压缩（compaction）标记 |
| `Current runtime context. This snapshot supersedes...` | 运行时上下文快照 |
| `<task-notification>` / `The coordinator sent a message while you were working` | 编排器注入消息 |

另外同一成员的几十个**同前缀小文件**（几 K-几十 K、session 名递增）常是同一自动化会话的碎片，不必逐个看。

**体量≠经验密度**：个别 key（如 sunlaibing）一天可达 10-25M tokens，但主体是自动化管线流量——按会话文件大小和提问特征判断，不按 key 的总 token 判断。

**已知去重盲区（已内置二次去重）**：部分 harness 会对同一长对话以不同 session_id 反复快照（如 murphy/hanjinhao 出现 17-30 个提问完全相同的渐变副本）。distill_extract.py 内置 pass 1.5：按 `(key_name, 首个用户提问 hash)` 二次聚合，同一对话只留消息最多的快照。

**富矿特征**：单文件 >100K、人类提问是口语化中文长句（描述具体资产路径/现象）、多轮来回。

## 编排重度用户的流量结构（跳过规则的唯一例外）

「机器人流量直接跳过」对编排重度用户（用 Orca/多 agent 编排跑工作的成员，如 sunlaibing 单日 600+ 会话）有一个系统性盲区：**该用户本人当天的工作成果大部分产在 worker 会话里**，而 worker 会话按上表特征全被判为机器人流量——照规则跳过后，层2 只剩一句「仅自动化流量」，整条工作线丢失。

这类用户的流量是四层结构，只有前三层可跳：

| 层 | 特征 | 处置 |
|---|---|---|
| 蒸馏/审核自动化 | 无 prompt 小文件、`经人工审核确认的知识` 写入 | 跳过 |
| 编排 worker | `You are working inside Orca...dispatched worker`、`review_input.md` 驱动 | 跳过正文，但**记归属**（worker 干了什么要进主人的层2） |
| skill 抽取 sub-agent | `You are the Skill extraction sub-agent.` | 跳过 |
| **session_summary 重放** | user 消息是 JSON：`首个用户目标：…最近用户目标：…会话结果：…` | **高保真信息源，必读** |

关键系统属性：memory-hub 的蒸馏管线会把每个已完成会话浓缩成 `首个用户目标/最近用户目标/会话结果` 三段式摘要在网关里反复重放（同一摘要在一天内出现多次）。这些重放文件只有几 K-几十 K，但**信息密度是全天最高的**——「会话结果」段就是该工作的最终结论与产出清单，正好补上 worker 正文里读不到的首尾。编排重度用户的层2 应以重放摘要为骨架、以 worker 正文为佐证，而不是按文件大小精读。

聚类方法：按首条 user 消息的 JSON `"text"` 字段前缀聚类（`首个用户目标` / `经人工审核确认的知识` / `(no-prompt)`），同一目标的多次重放只读最长一份；再按时间轴把目标串成线（首例与收官结论通常是用户最关心的两端）。
