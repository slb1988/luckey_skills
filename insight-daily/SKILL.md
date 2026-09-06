---
name: insight-daily
description: 每日人物洞察提炼工具。在用户要求“每日洞察”“跑人物画像洞察”“日记生成后提炼”“查看洞察 run”或希望从当天 Obsidian 日记提炼人物画像候选时使用；它只上传 DailySucc、TODO、决策、长期目标变动等相关分节，触发并轮询 Memory Hub insight run，并保留可离线复核的内容寻址 manifest。
---

# Insight Daily

在 `daily-report` 完成当天日记后运行本 skill。两者是串联关系：`daily-report` 负责生成日记，本 skill 负责提炼洞察；**不要修改或把洞察步骤塞进 `daily-report`**。

## 入口

```bash
SKILL_DIR="<本 SKILL.md 所在目录的绝对路径>"
python3 "$SKILL_DIR/scripts/insight_daily.py" run --date YYYY-MM-DD
```

常用参数：

- `--date YYYY-MM-DD`：缺省为本地当天。
- `--note 02_notes/daily/YYYY-MM-DD.md`：显式指定 vault 内日记；缺省从 Daily Notes 配置推导。
- `--person-id <id>`：显式指定人物；缺省由 Hub 解析当前 owner 的唯一 active self person。
- `--dry-run`：只在本地解析、校验并写 manifest，保证零网络请求。
- `--json`：输出适合自动化消费的单个 JSON 对象。
- `--timeout <秒>`：input/run 后轮询到 `done`/`failed` 的总等待预算。

脚本只使用 Python 标准库。它沿用 Memory Hub 的环境约定：

- `MEMORY_HUB_API_KEY`（缺失时读取 install 已写入的用户级持久配置）；
- `MEMORY_HUB_CLIENT_USER_ID`（兼容 `CLIENT_USER_ID`，再回退 `.team/settings.local.json` 与既有 client profile）；
- `MEMORY_HUB_URL`（兼容 `BASE_URL`，缺省沿用 Hub 默认地址）；
- `MEMORY_HOOK_STATE_DIR`（manifest 写到其 `insight-daily/manifests/` 下）。

不要读取、打印或写入 `.env`，也不要把 token 放进命令行或 manifest。

## 工作流

1. **定位日记**：解析 `luckey/.obsidian/daily-notes.json` 的 `folder`，组合 `YYYY-MM-DD.md`。路径必须留在 vault 和配置的 Daily Notes 目录内；绝对路径、`..`、反斜杠或 symlink 越界一律拒绝。
2. **只提取存在且非空的相关 H2 分节**：`DailySucc`、`TODO`、决策、长期目标/长期目标变动；保留重复 heading、CJK 原文与其嵌套小节，不上传整篇日记。
3. **本地证据校验**：对日记原始字节、上传分节和每个 `heading + Lx-Ly` locator 分别做 SHA-256 与逐字切片校验。校验失败时不得发请求。
4. **提交 input**：`POST /v1/insights/daily/{date}/input`，请求 schema 固定为 `insight-daily-input/1`；同内容由 Hub 幂等返回同一 input。
5. **创建 run**：使用服务端返回的 `input_id` 调 `POST /v1/insights/daily/{date}/run`，schema 固定为 `insight-daily-run/1`；不要让服务端猜“最新 input”。
6. **轮询**：只依赖 owner agent 可见的最小状态 `status/sources_total/sources_processed/proposals_created/error`，直到 `done` 或 `failed`；超时后保留 run id，不能自动调用 session-token-only retry。
7. **汇报**：输出提案数、run id、manifest 路径和人物中心 dashboard 深链。`failed`/超时必须明确返回非零。

每个阶段都会写一份内容寻址 manifest；最终 manifest 至少包含日记相对路径/hash、分节 heading 与行 locator、分节总 hash、`input_id` 和 `run_id`。同一份 manifest 的文件名就是其规范 JSON 的 SHA-256，便于发现本地篡改。

## 离线复核

```bash
python3 "$SKILL_DIR/scripts/insight_daily.py" verify \
  ~/.local/state/memory-hub-hook/insight-daily/manifests/<sha256>.json
```

`verify` 只重读 vault 原文并验证 manifest、note hash、分节逐字内容和 locator；它不调用 LLM，也不访问或上传到 Hub。可加 `--json` 获取结构化结果。

## 输出示例

```text
Insight Daily done: 4 proposal(s), run run_01...
Manifest: ~/.local/state/memory-hub-hook/insight-daily/manifests/ab12....json
Dashboard: http://10.77.77.6:9288/#persona?person=person_01...&section=proposals
```

## 可操作错误

- `NOTE_NOT_FOUND`：先运行 `daily-report`，或用 `--date/--note` 指向已生成日记。
- `NO_RELEVANT_SECTIONS` / `EMPTY_SECTIONS`：补写至少一个目标分节的实际内容；模板占位不上传。
- `PERSON_NOT_FOUND`：在人物中心创建/激活本人的 self person，或传 `--person-id`。
- `UNAUTHENTICATED` / `MISSING_API_KEY`：重新生成并安装有效的 Memory Hub agent token。
- `RUN_FAILED`：打开 dashboard 查看提案/run 状态；不要自动 retry。
- `POLL_TIMEOUT`：保留输出的 run id，稍后在 dashboard 查看；重新运行相同 input/run 是幂等的。

当用户只说“查看洞察 run”时，优先使用最近一次命令输出或 manifest 中的 `run_id` 与 dashboard 深链；不要为了查看状态重复上传日记全文。
