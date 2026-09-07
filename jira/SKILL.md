---
name: jira
description: Jira 当前待办与每日工作计划分析。通过 .env 中的 JIRA_TOKEN/JIRA_BASE_URL 读取当前用户在 Jira、Sprint 或 BigPicture Box 中的任务，按天缓存快照，分析优先级、容量、跨 Sprint 遗留和协作需求，并记录用户当天选择。用户提到 Jira 待办、今天做什么、每日任务、当前 Sprint/迭代、BigPicture 链接、PL-* 工单、再看一下待办或刷新 Jira 时都应使用本 Skill。
---

# Jira 每日待办

从 Jira 获取当前用户在指定 BigPicture Box 中的任务，生成可执行的当日计划。默认每天只生成一次网络快照；同一天后续查询复用本地缓存，既减少 Jira 压力，也保证编号和计划上下文稳定。

## 资源

- 日常拉取、缓存、分析与输出规则：[`references/daily-todo-workflow.md`](references/daily-todo-workflow.md)
- Jira API、环境变量与排障：[`references/api-and-troubleshooting.md`](references/api-and-troubleshooting.md)
- 确定性拉取脚本：[`scripts/jira_daily_todo.py`](scripts/jira_daily_todo.py)
- 本机每日快照：`assets/cache/`（已忽略，不提交）

处理当前待办、每日计划或协作分析时，先读 `references/daily-todo-workflow.md`。只有配置、认证、JQL 或接口报错时再读 API 排障参考。

## 快速工作流

1. 从用户给出的 BigPicture URL 解析 `/box/<BOX_ID>/`；没有 URL 时使用 `.env` 的 `JIRA_BOX_ID`。
2. 运行脚本。它优先读取当天同一 Jira、Box、Token 身份对应的缓存；不存在才访问 Jira：
   ```bash
   python <skill-dir>/scripts/jira_daily_todo.py --url "<BigPicture URL>"
   ```
3. 读取脚本打印的缓存路径，依据参考文档输出任务快照、风险、今日计划和协作项。
4. 用户再次说“看看 Jira 待办”时仍运行脚本，但不要加 `--refresh`；应看到 `source=cache`。
5. 只有用户明确说“刷新、重新拉取、忽略缓存”时才加：
   ```bash
   python <skill-dir>/scripts/jira_daily_todo.py --refresh
   ```
6. 用户选择了当天事项后，将其解析成工单 Key 后写入快照；不要只保存易漂移的序号：
   ```bash
   python <skill-dir>/scripts/jira_daily_todo.py \
     --focus PL-123 PL-456 \
     --assist PL-789 \
     --note "主任务与辅助检查"
   ```

## 行为边界

- 默认只读。除非用户明确要求，否则不要评论、转状态、改经办人或调整 Sprint。
- 不输出 Token，不把 Token 写入缓存，也不把 `assets/cache/` 加入版本控制。
- 区分 Jira 事实与建议：字段为空时明确说明，不要把建议排期描述成 Jira 已配置的日期。
- 用户用“1、2、3”指代任务时，以本会话最近一次展示的编号为准，随后持久化对应的 `PL-*` Key。

## 示例

- “看看今天 Jira 有什么要做” → 当天首次访问 Jira，之后使用缓存。
- “再分析一下刚才的待办” → 直接读取当天缓存。
- “这个 BigPicture 链接里的任务呢？” → 从 URL 提取 Box ID，配置的 `JIRA_BASE_URL` 仍优先。
- “今天做 1、2，3 只辅助看看” → 将最近报告中的编号解析为 Key，记录 focus/assist 计划。
