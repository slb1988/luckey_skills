# PLN_TaskAiReview 失败通知链路（TeamCityLogParserInformer）

## 链路结构

`TaskAiReview.kts` 末尾 `Log Analysis Notification` 步（RUN_ONLY_ON_FAILURE）→ 读 CL 号 → 调
`DevOps/TeamCityLogParserInformer.py --cl=<CL> --job-result=FAILURE`。

- informer 脚本由构建机在构建失败时**现 sync `//depot/DevOps`** → 提交即生效，无部署环节。
- informer 被 5+ 构建类型共用（TaskBuildUELinux / BuildProject / TaskAiReview 等）→ 任何行为变更必须做成 opt-in flag，默认行为不能动。

## 收件人归因与路由语义（脚本原语）

| 维度 | 行为 |
|---|---|
| 默认归因 | 正则扫构建日志提取错误文件 → `find_modifiers` 查文件最近修改人作为收件人 |
| `--use-cl-author` | opt-in；CL 提交者兜底（`changelist_authors` P4 查询 → User 表 → open_id），不显式传则不启用 |
| `--feishu-env prod` | 私聊路由（bot 单聊，按 User 表 open_id 发） |
| 未传 `--feishu-env` | 群机器人 webhook（默认 prod 群） |

## 已确认根因（2026-09 代码走读，修复前现状）

1. **CL 身份错配**：kts 传 `--cl` 用的是 `Saved/latestCL`（流头 CL），不是被评审的 shelved CL（`%env.unshelve%`）——即使查 CL 作者也会查到一个无关的最后提交人。正确源：`%env.unshelve%` 优先，0/空时回落 latestCL。与 FlowAiReview「sync 的是 HEAD 而非被审 CL 基线」同源的 head-vs-shelved 陷阱。
2. **「CL 提交者私聊」路径不存在**：prod 分支只消费文件责任人（`user_files_map`）；CL-author 兜底查出的用户在 prod 分支从未被消费，名单为空直接 fallback 群 webhook。即同时传 `--feishu-env prod --use-cl-author` 也走不到 CL 提交者私聊。

## 后端已有私聊兜底

后端 ai_review 对链尾失败本就有兜底：后端 LLM 静态分析 → `notify_ai_done` 私聊作者。
因此构建级 informer 群通知与后端私聊并存时，群卡既是错误归因又是冗余噪音——评估「是否保留 informer 步骤」时先知道这个兜底存在。

## 修复进展（2026-09-07）

已按「有 env.unshelve 就直接私聊该 CL 作者」定稿实现并验证（admin_sun_depot_7184 CL 1503，待用户提交）：
kts 按 `%env.unshelve%` 分支传 `--cl=<shelved CL> --notify-cl-author`；informer 新开关
`--notify-cl-author`（opt-in，默认路径零变化）——跳过 find_modifiers 归因，`changelist_authors`
直查 CL 作者（shelved CL 已实测无权限问题，回退 `get_userinfo/<p4_userid>`），bot 私聊发送，
群 webhook 全抑制，`--feishu-env test` 仍路由 xuzhiyang 私聊用于安全验证。排障以 CL 1503 后的代码为准。
