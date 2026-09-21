# lark-cli 拉取群消息（飞书语义源）

无飞书日报总结参数时，用 lark-cli 直接拉取目标日期的群消息，替代人工总结作为第三路语义数据源，按 SKILL.md Step 4 的合并规则与 AW / P4 数据三路合并。

## 环境约束（2026-09 本机已确认）

- `lark-cli im +messages-search`（跨群全局搜索）所需 scope **未授权**，调用报权限错误，不要依赖。
- 唯一可行路径：`+chat-list` 枚举全部群 → 逐群 `+chat-messages-list` 按日期窗口拉取。

## 流程

1. `lark-cli im +chat-list --page-all` — 列出当前用户加入的全部群。必须显式 `--page-all`：默认只回单页 20 条（响应 `meta.pagination.complete=false` 即未拉全；实例：全量 134 个群）。`--types` 只接受 `p2p,group`，默认 group 已含话题群（topic），不要传 `topic`。
2. 逐群拉目标日期消息（批量扫描加 `--no-reactions`，跳过 reactions enrichment，请求数减半）：
   ```bash
   lark-cli im +chat-messages-list --chat-id oc_xxx --start 2026-09-18 --end 2026-09-19 --page-all --no-reactions
   ```
   `--start/--end` 日期-only 或带时区的 ISO 8601 均可；end 传次日日期覆盖目标日全天。
3. 按活跃度筛选：当日无消息的群跳过（实例：134 群中 21 个活跃、共 751 条），活跃群消息全部过完。
4. 用户本人发言单独按 sender 过滤确认一遍，避免遗漏「用户自己在群里说了什么」。

命令完整参数见全局 lark-im skill（`+chat-list` / `+chat-messages-list` / `+messages-search`）。

## 消息 JSON 结构（解析口径）

`+chat-messages-list` 输出中，消息正文在每条消息的**顶层 `content` 字段**（JSON 字符串，内含 `text`），不在飞书 API 文档式的嵌套 `body.content` 里。写提取脚本按顶层 `content` 解析；若解析结果为空，先打印一条原始消息确认实际字段路径，不要凭文档假设嵌套结构（2026-09-20 会话实测踩过）。

## 日记落盘要求

走 lark-cli 路径时，除 DailySucc 合并条目外，在日记中追加「## 飞书消息摘要」一节（DailySucc 之后、App 使用时长之前）。摘要口径（用户 2026-09-20 定版，优先于此前的全群归纳口径）：

1. 只总结用户**实际参与发言/讨论/推进**的工作，不包含只是围观但没有参与的内容
2. 重点突出：用户主动发起的讨论、回复解决的问题、发布的成果
3. 剔除：没有发言的群讨论、没有参与决策的事项
4. 按优先级排列：技术/开发工作优先，流程/提醒类其次
5. 保持精简，不要发散
