# 手动批量上传历史 session（upload_sessions.py）

> 从 SKILL.md 移出的批量归档细节。live hook 归档机制见 [agent-integration.md](agent-integration.md)；Codex 格式解析等排障见 [troubleshooting.md](troubleshooting.md)；误归档后的清理见 [cleanup-misscoped-sessions.md](cleanup-misscoped-sessions.md)。

`scripts/upload_sessions.py`（仅标准库）把任意机器/目录下的历史 session 记录（`.jsonl`）批量上传到
Hub，每个文件成为独立 session（`{source}:{原始session_id}`），并附一条可检索的 `session_summary`
记忆。适用于 hook 上线前的历史归档、其他电脑导出的 session 等（`memory_hook.py` 没有 backfill 子命令，
capture 只处理当前 live transcript）。

配套脚本 `scripts/backfill_missed_pi_sessions.py` 回答「有没有漏传」并一键补传（本机专用，2026-08-22 加入）。
检测原理：Hub `sessions` 表是全部已归档 session 的 ground truth（id 形如 `pi:<project>:<uuid>`），本地
pi session 文件名 `<ts>_<uuid>.jsonl` 的 uuid 即 session id，两边按 UUID 求 diff（local − hub）=
全量漏传清单——比查 spool/pi-trace 更直接，且能覆盖 hook 上线前的历史 session。脚本再按首条 user 消息
签名排除 auto-skill extraction 等 LLM 分析子 session，最后以 `--hook-namespace` 调 upload_sessions.py
幂等回填（可中断重跑）。

## 两条铁律（2026-08-20 用户定版，违反被明确纠正过）

1. **默认必须双资产一起传（`--hook-namespace`）**：快照 + 完整 session 文件一次到位，禁止先用普通
   模式传单资产、再 `--backfill-full` 补——那是返工。普通单资产模式只用于确实没有完整 jsonl 源的场景。
2. **project 归属必须先经用户 review**：任何批量上传实际执行前，先 `--dry-run` 生成每个 session 的
   归属 project 清单交给用户确认，用户点头后才去掉 dry-run 执行；不得自作主张选定 `--project-id`
   （包括"按 skill 文档默认 agent-history"也不行——文档默认值也要用户确认）。

## 历史 session 文件位置（Windows）

- Claude Code：`%USERPROFILE%\.claude\projects\<slug>\*.jsonl`（文件名即 session UUID）
- Pi：`%USERPROFILE%\.pi\agent\sessions\<slug>\*.jsonl`（文件名 `<UTC时间戳>_<uuid>.jsonl`，单项目可积累上千个）
- Codex：`%USERPROFILE%\.codex\sessions\`（递归子目录，单机可积累数百个、上百 MB）

slug 方案各家不同：`E:\sununity` 在 Claude 是 `E--sununity`，在 Pi 是 `--E--sununity--`——定位时按
`sessions/` 实际列表匹配，不要自行推算。

## 幂等保证

对包装后的归档文档（`agent-session-archive/1`，服务端要求 session 文件必须是合法 JSON，
原始 jsonl 不行）计算 SHA-256；上传前比对远端 latest 版本，一致则 `skipped`；所有写操作带确定性
`Idempotency-Key`，中断可直接重跑。内容变化时自动 append 新版本。

## project 归属与本机映射

本机 project 归属是**机器级映射（字典）**，写在 state dir 的 `project-aliases.local.json`（
`install_hooks.py install --project <id>` 写入 `{"aliases":{"*":"<id>"}}`，不进 git、不随 skill
模板扩散，其他机器/用户不受影响）。优先级：`--project`/`--project-id` 显式参数 > 本机 local 映射 >
共享模板（`assets/project-aliases.json` 部署）> cwd 派生兜底；映射里 `"*"` 是 catch-all（如
`{"*":"nas"}` = 本机全部归 `nas`，具体条目如 `{"memory-hub":"memory-hub"}` 优先于 `*`）。本机映射
一旦设置，capture/search/批量归档默认按它归 project，与其他机器的项目完全隔离。只有显式
`install --project <id>` 才会新建或修改 catch-all；普通 install 不询问、不根据主机名猜测，只保留
已有配置。**多 workspace 工作站不应设置 `"*"`，而应依赖 cwd 派生或具体目录映射**。**本机映射只能写系统目录
（state dir），绝不允许改 skill 模板 `assets/project-aliases.json` 来映射本机名**（那会污染共享模板、
影响其他用户）。

本机 local 映射（`project-aliases.local.json`）未设置时，不传 `--project-id` 会按**每个 session 的 cwd 文件夹名**逐个派生
project——全机批量归档会散落到 `admin`、`sununity`、`MainDev`、`ObsidianVault` 等十几个 project
（实测 3 个 pi session 落进 2 个 project）。检索按 project 隔离，散落后必须逐 project 切换才能搜全。
批量归档历史 session 可考虑 `--project-id agent-history`（hook 归档主库）集中存放，**但选定前必须先给
用户 review 归属方案，确认后才执行**。

归档命令定版与别名映射一览见 [projects.md](projects.md)「Project 别名定版」一节。

## 用法

```bash
SKILL_DIR="<本 SKILL.md 所在目录的绝对路径>"
# 指定 project，自动识别 claude/pi/codex，agent 按来源分类（claude-code/pi/codex）
python3 "$SKILL_DIR/scripts/upload_sessions.py" --project-id unity2018 <session文件或目录>...
# 干跑只看扫描结果，不碰服务器
python3 "$SKILL_DIR/scripts/upload_sessions.py" --project-id unity2018 --dry-run <目录>
```

- `--user-id` 默认取 hook 的 client-profile；`--source/--agent-id` 可强制来源与身份。
- 目录会递归扫描 `*.jsonl`；`--limit N` 可先小批量验证。
- 大量上传后 memory 经 outbox 异步投递 Graphiti，`indexed` 状态用 `GET /v1/memories/{id}` 跟踪（索引状态定义见 [api-notes](api-notes.md)）。
- 低价值过滤（启发式 + 可选 LLM）与归档摘要三段式 distilled 的规则与 hook 侧共用，见 [agent-integration.md](agent-integration.md)「会话标题与低价值过滤判定」。
