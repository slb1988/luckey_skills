# Memory Hub 排障与调试参考

> 从 SKILL.md 移出的排障/调试条目。部署、启动、备份类运维见 [deploy.md](deploy.md)；dashboard 开发/部署见 [dashboard.md](dashboard.md)。

## 检索

### 编辑器内 `memory_search` 0 命中：用 CLI 复现检索链路

编辑器内 `memory_search` 0 命中时，绕过扩展用 CLI 复现：pi/claude 的记忆扩展只是薄封装，实际检索全部在 `scripts/memory_hook.py search`（扩展源码里 grep 不到 project/检索逻辑属正常）。`/usr/bin/python3 scripts/memory_hook.py search "<query>" --project <id> --limit 20 --json` 与编辑器内走同一链路，且 `--project` 可探测当前 cwd 派生 scope 之外的项目（如 agent-history、maindev），`--json` 可看原始返回结构排除展示层问题。

### Graphiti 语义检索的噪音底线（返回非空 ≠ 命中）

Graphiti 语义检索噪音底线高：乱查（大小写无关）也会返回"近似"结果——**返回非空 ≠ 命中，目标不在 top-N ≠ 不存在**。判定"没有这条记忆"前先调大 `--limit`（默认 10）并换关键词重试，再按 project scope 排查。live hook 同样按写入时 cwd 文件夹名派生 project：Windows 端写的记忆散落在 maindev/unity2018/agent-history 等，Mac 端 ObsidianVault 会话默认只能看到 obsidianvault project——跨机器"重启后搜不到"几乎都是 scope 隔离而非故障。

## Hook 与 Pi 扩展

### v4 AFK 防抖的 capture 丢失窗口（v5 已修复）

v4 AFK 防抖的丢失窗口（2026-08-21 实测定性，**v5 已修复**）：v4 中 agent_end 后扩展只写
`capture_schedule`，进程在防抖到期前被杀（直接关终端不触发 `session_shutdown`）则尾部永不
capture。v5 改为 agent_end 立即 enqueue-only 落 spool + write-ahead marker，丢失窗口压到
「marker 落盘前的进程内微秒级」。v5 遗留观测注意：enqueue 链路在脚本侧仍无 hook-trace
（`trace_event` 只包 search），但扩展侧 pi-trace 的 enqueue_done 带 hook 返回的严格契约
（result/job_id/sha256），排障先看 enqueue_done.outcome 再去 spool 交叉核对。

### v5 设计定版依据（2026-08-23 codex 独立评审）

v5 设计定版依据（2026-08-23 codex 独立评审，报告 `.claude/plans/Pi归档启动补传.review.md`，
原计划 2C/7M 被打回重写）：① **fire-and-forget 的 enqueue 没有持久化边界**（评审 C1）——
handler 在子进程落盘前返回等于没保证，故 agent_end 必须 await（有上限超时，超时不杀子进程、
marker 留下次 catch-up）；② **spool supersede 按 INSERT 先后而非 transcript 新旧**（评审 C2，
既有缺陷）——并发 enqueue 会让旧快照后提交反向淘汰新快照，故 memory_hook.py 新增
per-session enqueue 文件锁（`locks/enqueue-*.lock`，持锁后才读 transcript）；③ **flush 与
enqueue 有对象删除竞态**（既有缺陷）——flush 先原子认领 queued→uploading（10 分钟租约，
崩溃回收），supersede 只碰 queued，complete/fail 带状态条件防陈旧写者复活；④ 恢复记录用
**pending-enqueue marker**（write-ahead，只代表「这次 enqueue 未确认」），不做 open-session
登记——pi transcript 是 lazy 落盘，session_start 时文件可能不存在，登记会被多开窗口误删。
capture 新增 `--no-flush`（只入队）与 `--json`（严格机器可读契约，异常非零退出；不带 --json
的旧调用行为不变）。测试三层：python 单测（含 barrier 强制逆序的并发回归）+ Node e2e +
真实脚本冒烟。实施计划：`.claude/plans/Pi归档启动补传.md`。

### 「hook 是否生效」必须分两层验证

回答「hook 有没有成功安装/生效」必须分两层验证：`install_hooks.py check` 全绿只证明**安装副本与模板一致**
（静态层，且历史上存在过误报 ok 的案例）；运行层证据看 pi-trace.jsonl **最后一条 `session_start`**——其
`ext_version` 与模板版本一致、且时间戳属于当前会话，才证明扩展真的被 pi 加载并正在 firing。check 绿但本会话
trace 无 `session_start` = 扩展未被加载（查扩展路径/加载冲突），两层都过才能回「已生效」。

### 审计本地 session 是否漏传 Hub（三方交叉比对）

审计「本地 session 是否漏传 Hub」的交叉比对法（2026-08-21 全流程验证）：① spool.sqlite3 当日 job 中 `status='completed' AND remote_version IS NULL` = 被 LLM 过滤（skipped_meaningless）——被过滤 job 的 session 早期版本通常已在 Hub，丢的只是最后一次 capture 的尾部增量；② pi-trace 有 capture exit 0 但 spool 无 job = 早退（extraction 子 session 首消息签名 / transcript 从未落盘的「幽灵 session」走 `is_file()` 早退 / 未查明原因）；③ 拿本地 session 文件与 Hub latest 版本核对内容覆盖度。LLM 过滤器只按快照**尾部一对 user/assistant** 判定：以决策讨论/功能确认问答结尾的 session 易被误判低价值（单日实测 2 例误伤），评估过滤质量时重点抽查这类结尾。

### install 后同一 shell 里 check 显示 identity missing 是预期

在刚执行完 install 的**同一 shell** 里跑 `install_hooks.py check --agents auto`，`identity.source` 显示 `missing` 是预期——user-id 环境变量已写入 `~/.profile`/`~/.zprofile` 但当前进程未加载；新开终端或重启 agent 后即正常。不要据此重装或重复 configure。

### Windows 上 hook 全静默 exit 127（模板 python 路径硬编码）

agent-integration.md 的 install/configure 示例命令是 macOS 写法（`/usr/bin/python3`、`/Users/sun/...`）。
Windows 上曾发现扩展配置里原样保留了 `/usr/bin/python3` 这个 Unix 路径导致 hook 无法执行——Pi 扩展模板 v2
把 python 路径硬编码为 `/usr/bin/python3`，Windows 端 spawn 全部 exit 127 静默失败（pi-trace.jsonl 里
recall/capture 全红），且 check 因「副本与模板一致」误报 ok。**v3 起模板改为 `__PYTHON_JSON__` 占位符，
由 install_hooks.py 注入本机解释器路径**（优先 /usr/bin/python3，否则 sys.executable）；老机器 check 报
outdated 后重跑 install 即修复。排查「关窗提示有进程未结束」是否 hook 残留时，按命令行列 python.exe 分辨：
本机常驻 python 通常是 UnrealMCP 和 pytest，与 memory-hook 无关；memory_hook.py 是逐事件短进程，正常不常驻。

### 全员上传 401：服务端切生产模式后 hook 静默积压（无报错、无丢失）

服务端切到多用户账号体系（生产模式强制 `mhu_` token，2026-08-22 实例）后，未配 `MEMORY_HUB_API_KEY`
的机器所有上传返回 `401 UNAUTHENTICATED: MEMORY_HUB_API_KEY is required outside development`，但
**hook 完全不报错**——capture 照常落本地 spool，job 持续 queued 积压（实测积 13 个，codex 5 + pi 8，
零丢失）。表面症状只是「session 好像没被上传」。诊断：对比最后一次成功上传与首个 401 的时间点即可
定位服务端切换窗口。修复：① 网页端生成 `mhu_` token，先用它调 `GET /v1/projects` 验证 200；② 把
`export MEMORY_HUB_API_KEY=mhu_...` 追加进 `~/.profile`/`~/.zprofile` 已有的 memory-hub identity
标记块（当时 install 只持久化 USER_ID），并按凭据约定同步 `~/.env`
（chmod 600）；③ `memory_hook.py flush` 一次清空全部积压。注意已在运行的 agent 进程环境里没有新
变量，重启前 capture 仍 401 落 spool（不丢），重启 agent/终端后再补一次 flush 兜底。
2026-08-23 起两处闭环：`install_hooks.py check` 的 `auth` 项自动检出此状态（未配 key + 服务端
强制认证 → check 失败并按平台给出持久化指引）；install 会沿用 profile/注册表已有的 key（或
`--api-key` 传入）一并持久化，升级重装不再静默抹掉 key。

### Spool 积压 job 持续 `SCOPE_FORBIDDEN` 不自愈

Spool job 在 capture 时固化 `user_id`（这是设计，防止补传到错误用户）。副作用：身份配置变更（如 install 写入新的 `MEMORY_HUB_CLIENT_USER_ID`）之前积压的 queued job 仍带旧身份，flush 时持续报 `SCOPE_FORBIDDEN` 且不会自愈（实测一次积压 11 个）。看到 spool 反复 403 时直接清理这些旧 job，不要当作服务端权限配置问题排查。

### 上传 401 积压与 spool FIFO 队头阻塞

spool 的 flush 是 **FIFO 队头阻塞**：队头 job 持续失败重试会饿死后面 attempts=0 的 job（401、网络错误同理）。
2026-08-22 实例：key 持久化进注册表**之前**被 Orca/终端拉起的 agent 进程环境里没有 `MEMORY_HUB_API_KEY`，
capture/flush 全部 401 落 spool 堆积，而当时只有 check 有注册表回退（报 `token_accepted: true`）——两层结果
不一致曾造成误判。2026-08-25 起 `memory_hook.py` 的 `read_persisted_env_var` 会在进程环境缺失时回退读
注册表/profile，新 spawn 的 hook 进程 401 自愈、无需重启 agent；但**已积压的 queued job 不会自动清**——
修好 key 后仍需手动 `memory_hook.py flush --limit 100`（重复跑到 queued=0）排空。

### `enqueue_done outcome=skipped_capture_env` = 快照根本没进 spool（skipCapture 环境污染）

`enqueue_done outcome=skipped_capture_env` 表示快照根本没进 spool（write-ahead marker 直接删，不是上传失败，补传也不会捞到）：memory-hub 扩展自身的 `skipCapture` 是**加载时缓存**的，但 spawn 出的 hook 子进程继承的是**当前**进程环境——任何扩展把 `MEMORY_HUB_SKIP_CAPTURE=1` 挂在共享 `process.env` 上，窗口期内所有 capture 都被整段跳过。实测污染源：auto-skill 扩展在 extraction 子 session 的分钟级 `await prompt()` 期间持有了这个变量（已修复收窄到 createAgentSession/dispose 两个毫秒级窗口）；现象特征是「同机其他项目正常 enqueued、某项目连续 skipped_capture_env」。hook 侧另有 transcript 首消息签名检测（`skipped_extraction`）兜底，所以收窄窗口是防误判不是防泄漏。

### 幂等重放拿回过期 upload = FIFO 永久队头阻塞

（2026-08-29 实例，job 1210 卡 106 次、28 个 job 饿一天）：initiate 上传的幂等键是确定性的，服务端按 key 原样重放首次响应，上传会话 TTL 10 分钟过期后重试拿到的仍是同一个失效 upload_id；PUT 失效 URL 时服务端不读 body 直接 404/410 并关连接，大 body 客户端收到的是 WinError 10054（连接重置）而非 404，被误判为瞬时网络错误无限重试。特征：flush 永远 `failed:1`、`last_error=WinError 10054`、queued 堆积但 search 完全正常（GET 不受影响）。排查路径：spool.sqlite3 jobs 表查队头 last_error → curl 复现 GET/POST 正常 → 跟到 PUT expired upload。修复：`_upload_file` 检测 file status `expired` / PUT|complete 失败后换全新幂等键重建上传会话（至多 3 轮，retry_salt=job.attempts），`request()` 把裸 OSError 包成 HubError 让 full 上传降级生效。服务端待修：`initiate_upload` 幂等重放应检查 upload 是否过期、过期则新建而非原样返回。

### session 归错 project（全落某个 catch-all）先查本机映射

<memory category="troubleshooting">
**session 归错 project（如 admin_sun_depot_7184/MainDev/ObsidianVault 全落 `project:sun`）先查本机 catch-all**：state dir `project-aliases.local.json` 里 `{"aliases":{"*":"<id>"}}` 是 `install_hooks.py install --project <id>` 写入的整机 catch-all；2026-08 之前的旧版还可能因 agent 伪终端空输入，把主机名建议值以 `source: "prompt"` 静默写入；旧版还有第三条写入路径（local JSON「老是被修改」的机制）：`main()` 只要 `resolve_machine_project()` 返回 project_id——含 `source=existing` 仅仅读到已有配置——就调 `install_machine_project()` 把文件重写一遍，每次普通 install（skill 更新、agent 重装）都重断言错误 catch-all 并刷新 `updated_at`。`atomic_write` 每次覆盖前生成 `.memory-hub.bak`，state dir 里残留的多个含 catch-all 的 bak（updated_at 相隔几十秒 = 连续两次 install 的痕迹）不会被读取，可直接删。共享模板 `assets/project-aliases.json` 只有子目录/特定目录条目（backend/frontend→admin_sun_depot_7184、sununity→unity2018），**没有顶层目录自映射**；解析是 `aliases.get(name, aliases.get("*", name))`，未列名 cwd 全部落 `*`（2026-08-28 实测复现）。`--project` catch-all 只适合专用单项目机器（NAS→nas），多项目工作站用了会吞掉所有未显式列名的项目——应删 `*`，按需保留具体目录映射（显式条目优先于 `*`）。修复定版 commit `22c6589`（2026-08-30）：交互 prompt 路径整个删除，新 `apply_machine_project()` 只在显式 `--project`（`source=flag`）时写文件，已有配置只报告不重写；回归测试在 `scripts/tests/test_install_hooks.py`。排查路径：直接调 memory_hook.py 的别名解析实测各 cwd → spool.sqlite3 jobs 表按 local JSON mtime 分界统计错归 job。hub 上已错传的 session 不可变，按正确 project 补传只产生新版本，旧污染仍留在错 group。另注意：`.team/<member>/` 个人记忆若把错误配置记成「已固定，禁止重复确认」会固化错误，修复配置时需同步更正该条目。
</memory>

## 测试

### Windows 本机 pytest 稳定 13 个失败（平台性问题）

`scripts/tests/` 在 Windows 本机跑 pytest 稳定有 13 个用例失败（10 passed），失败点全在 tearDown 的 `shutil.rmtree`——spool.sqlite3 文件锁 PermissionError，属 Windows 平台既有环境问题（stash 验证未改动代码同样 13 败），不是 regression。评估改动是否破坏测试时对比改动前后的失败集合；要干净结果去 Linux/macOS 跑。

### macOS 跑 tests 的姿势坑与平台性失败

跑 `scripts/tests/` 的两个姿势坑（macOS 实测）：① `tests/conftest.py`（把 `scripts/` 加入 sys.path）**只在 pytest 下加载**，用 `python -m unittest` 必须 cd 到 `scripts/` 再跑，否则 import 失败；② macOS 上 `test_memory_hook` 同样稳定有 4 个平台性失败（如 `project_id_for_cwd` 的 Windows 路径断言，改动前干净检出复现），与 Windows 的 13 败同理——任何平台都不追求全绿，只对比失败集合差集。

## 批量上传

### Codex 新格式 session（首行 session_meta）解析

Codex 新格式 session 文件首行是 `session_meta` 记录，cwd 与 session uuid 只存在于该行的 payload 内、无法从文件路径推出。旧版 `upload_sessions.py` 不识别该格式时 cwd 全部丢失——实测 238 个 codex session 会全部落入兜底 project 且 session id 退化为文件名；已修补 `scan_session_file` 支持（dry-run 238/238 解析成功）。批量归档不熟悉的来源前，先 `--dry-run` 核对 cwd 解析率和 session id 形态（应为 `{source}:{project}:{uuid}` 三段式）再实际上传。

### Codex Desktop 新消息事件导致摘要全是「未提取到文本」

Codex Desktop rollout JSONL 可能同时保存 `response_item/message` 与
`event_msg/item_completed`。可见消息的权威事件是后者的 `UserMessage` / `AgentMessage`；
`response_item` 还可能带 developer、recommended plugins、AGENTS 等注入上下文，且文本块
类型使用 `input_text` / `output_text`。逐行混合解析会重复消息或把注入内容误当用户目标。

`scripts/session_messages.py` 是 live hook 与 `upload_sessions.py` 的共享解析器：新版 Codex
优先 `item_completed`，且 AgentMessage 只归档 `phase=final_answer`（旧格式无 phase 时兼容
保留），从而排除 commentary 进度更新；旧版优先 `user_message` / `agent_message`，最后才
回退 `response_item`。同一 resumed rollout 中新旧权威事件族会按事件位置合并，再逐条消耗
邻近且内容相同的 `response_item` 镜像；未匹配的 response item 才作为回退消息保留，避免
格式切换或重复短 prompt 时丢失较早轮次、错配镜像或重复整段消息。Desktop UI 注入的
`<user_action>`、`<turn_aborted>`、压缩交接摘要等协议记录也会排除；镜像匹配会先剥离
附件 `<image>` 包装，避免带截图的用户轮次重复。文本块兼容 `text` / `Text` /
`input_text` / `output_text`。排障时用
真实 rollout 文件统计 `extract_session_pairs(..., source="codex")` 的 role 数量，不要只看
Hub 已生成的占位摘要。

## 服务端（Hub 侧）

### POST /v1/feedback 曾会把目标 memory 判死（hotfix e081453 已修复）

<memory category="troubleshooting">
**POST /v1/feedback 会把目标 memory 判死（5a9366f 引入的 worker 缺陷，hotfix 前不要对需要保留检索的记忆发任何 feedback）**：`record_feedback()`（service.py:2662）落 `memory_feedback` 行后还发 outbox 事件（aggregate_id=memory_id），但 `OutboxDispatcher.dispatch_one()`（workers/outbox.py:49）只认 `graphiti.*` 事件，对 `memory_feedback` 抛 non-retryable GraphitiError；`_fail()`（outbox.py:304-311）terminal 失败时**不区分事件类型**、无条件 `UPDATE memories SET status='failed', error_code='GRAPHITI_PERMANENT_ERROR' WHERE memory_id=aggregate_id`。FTS 候选要求 `status='indexed'`（retrieval.py:97），所以一条 `relevant` feedback 就足以让目标记忆对**所有用户**从检索消失（比被禁的 `rejected` 破坏力更大；`rejected` 只抑制提交者本人但无回收站端点、不可逆）。**已定版修复 hotfix e081453（2026-08-30 部署验证）**：outbox 为 `memory_feedback` 加本地处理器（`_complete_local` 直接结算、不投 Graphiti，实测事件 70ms 内 completed、attempt_count=0），`_fail()` 的 memories 回写已限定 graphiti 类事件；post-fix smoke（relevant feedback → 200 accepted=true，等 10s 让 worker 跑一轮）后 memory 保持 `indexed` 且 `updated_at` 不被触碰——这是 hotfix 生效的直接证据。数据修复（恢复 `01a043eb` indexed、清 failed outbox、清 smoke feedback 行）已执行完毕，episode 在 Graphiti 完好无需 reingest。取证要点：`_fail()` 会改写 memory 行 `updated_at`，而修复 SQL `UPDATE status` 不触碰——`updated_at` 定格的是 bug 点火时刻，可据此区分故障时间与修复时间。另：本次 runbook 曾发生两个会话并发执行同一修复流程撞车（修复语句被抢先跑掉、影响行数与预期全不符）——授权写操作执行前先留只读基线、逐条核对影响行数，与预期不符立即停止报告，不要扩大范围。另两个验收事实：feedback 要求 `X-User-Id` 与 API key 绑定账号一致（release 服务器绑定账号是 `sunlaibing`，不是 `slb1988`）；search-v2 fusion 里 `fallback=graph_disabled / graph_candidates=0` 是既有状态（Graphiti 图检索未启用），不是回归信号。
</memory>

### 入库审核（triage）报 "unparseable llm response" = 上游 LLM 间歇性非法 JSON

<memory category="troubleshooting">
**入库 session 审核（triage）报 "unparseable llm response" 的根因是上游 kimi-k3 间歇性输出非法 JSON，不是解析代码/prompt/截断问题**（2026-08-30 重放失败快照实证，约 1/3 概率）：中文字符串值漏加引号（真实返回形如 `{"decision": "approve", "rationale": 记录了…}`），`json.JSONDecoder().raw_decode` 抛 `Expecting value`，`_parse_triage_response` 兜底落 `uncertain` + rationale "unparseable llm response"。temperature=0 压不住。重放已排除的假设（排查时别先怀疑这些）：HTTP 全 200、`stop_reason=end_turn`、输出仅 ~150 tokens（远低于 2048 上限）、content 结构 `[thinking, text]` 正常。两个结构性缺口：① **解析失败完全静默**——日志无任何输出、原始 LLM 返回不落盘，只能重放快照取证；② attempts 打满上限 3 后记录留 pending 不再自动重试，需人工重置 attempts 或 dashboard approve（当日 3 条误伤：hsbg-companion ×1、obsidianvault ×2，重放显示内容本身均会判 approve）。triage LLM 配置：kimi-k3 @ 10.77.77.4:8600（Anthropic 协议）。修复方向（截至 2026-08-30 未动代码，待决策）：解析失败时正则兜底抽 `"decision"\s*:\s*"(\w+)"` 与 rationale 段 / 追加「只输出严格 JSON」重试一次 / 失败时把原始返回截断写日志。
</memory>

### 入库审核显示 `LLM /v1/messages returned HTTP 400`

审核 LLM 走 Anthropic Messages API。Hub 默认显式发送 `thinking: {type: disabled}`，适配
默认开启推理的 Kimi/DeepSeek 兼容网关；上游非 2xx 响应正文会经过长度限制与凭据脱敏后
进入审核理由。若仍为 400，优先根据详情核对 `REVIEW_LLM_MODEL` 是否为网关实际加载的
模型 ID，其次核对 `REVIEW_LLM_BASE_URL` 是否为不含重复 `/v1` 的 Anthropic base URL。
