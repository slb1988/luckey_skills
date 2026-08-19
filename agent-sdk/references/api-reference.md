# pyauto_agent API 参考

> 面向实现/调试代理 agent。SDK 源码：`pyauto_agent/{app,executor,registration,workspace_lock}.py`。
> 当前版本 0.7.0。

## 目录
- [AgentApp](#agentapp)
- [@app.skill](#appskill)
- [app.run](#apprun)
- [消息路由与 handler 契约](#消息路由与-handler-契约)
- [注册 / 心跳 / 注销的 wire 行为](#注册--心跳--注销的-wire-行为)
- [AgentCard 生成](#agentcard-生成)
- [TaskState 与结果回传](#taskstate-与结果回传)

## AgentApp

`AgentApp(name, platform_url, public_url, description="", owner="", version="0.1.0", register_key="", heartbeat_interval=30.0, on_platform_deleted=None, tc_agent_name="", lock_ttl_seconds=1800, lock_acquire_timeout=3600.0, lock_poll_interval=30.0)`

| 参数 | 说明 |
|------|------|
| `name` | agent 名称，**平台全局唯一**（@名派发、name 唯一约束）。同名不同 url 注册被拒。 |
| `platform_url` | 平台根地址，如 `http://pyauto-server:5000`。SDK 拼 `/agent_platform/a2a/...` 调用。 |
| `public_url` | 本 agent 对**平台可达**的地址+端口，如 `http://10.20.30.40:9000`。平台注册时回抓 `<public_url>/.well-known/agent-card.json` 作连通性探测，并作为派发目标地址。末尾 `/` 会被去掉。 |
| `description` | 描述；平台缺省用它，前端展示。 |
| `owner` | 所有者用户名，前端展示/归属。 |
| `version` | agent card version 字段。 |
| `register_key` | 平台配置 `AGENT_PLATFORM_REGISTER_KEY` 时必填且需一致，否则注册 403。 |
| `heartbeat_interval` | 心跳间隔秒，默认 30。平台 Redis TTL 默认 120s，间隔应 < TTL/2 留裕量。 |
| `on_platform_deleted` | 平台删除/踢出本 agent 时的回调（410 或 `/_pyauto/shutdown` 触发，0.4.0 起）。**默认直接 `os._exit(0)` 退进程**——被踢即释放名字，重启重新注册即可回归；想只脱离平台不退进程传 `lambda: None`。 |
| `tc_agent_name` | 本 agent 所在 TeamCity 构建机名（0.5.0 起）。非空启用 workspace 互斥：每任务执行前经平台取该机的 `tc_agent_lock`，执行完自动释放；心跳上报 busy 供平台续租/空占回收。不在构建机上跑的 agent 不要传。 |
| `lock_ttl_seconds` / `lock_acquire_timeout` / `lock_poll_interval` | workspace 锁参数（锁 TTL / 等锁上限 / 等锁轮询间隔），仅 `tc_agent_name` 非空时生效。 |

## @app.skill

`@app.skill(id, name, description="", tags=None, examples=None)`，装饰一个 `(text: str) -> str` 函数。

| 参数 | 说明 |
|------|------|
| `id` | skill 标识；也是**消息路由前缀**（`"<id>: 参数"`）。多 skill 时靠它分流。 |
| `name` | 展示名，进 AgentSkill.name。 |
| `description` | 能力描述，进 card；缺省用 `name`。 |
| `tags` | 字符串列表，进 card 的 skill tags。**决定能否被平台 `skill_tag` 匹配/广播命中**，给有意义的 tag。 |
| `examples` | 示例输入列表，进 card，便于使用者理解。 |

- 至少注册一个 skill，否则 `run()` 抛 `RuntimeError`。
- **第一个注册的 skill 是默认 skill**：无前缀或前缀非已知 id 的消息都交给它。

## app.run

`app.run(host="0.0.0.0", port=9000, log_level="info")` — 阻塞。做三件事：

1. 用 `build_card()` 构 AgentCard，装 `DefaultRequestHandler(SkillRouterExecutor, InMemoryTaskStore)`，
   `create_agent_card_routes` + `create_jsonrpc_routes(handler, "/")` 组 Starlette，`uvicorn.run`。
2. `RegistrationClient.start()` 起守护线程注册 + 心跳。
3. `finally` 里 `reg.stop()` 注销。

> `port` 要与 `public_url` 的端口一致（示例里从 `public_url` 解析 port）。`host=0.0.0.0` 监听所有网卡以便平台可达。

## 消息路由与 handler 契约

`SkillRouterExecutor._route(text)`：
- `text` 以 `"<id>:"` 开头且 `<id>` 是已注册 skill → 路由到该 skill，冒号后（strip 后）作为 `text`。
- 否则 → 默认 skill，**原文**作为 `text`。

handler：
- **同步**函数，在 `asyncio.to_thread` 里跑，可放心阻塞（subprocess/文件/网络）。
- 返回 `str` → 作为 text artifact 回传，任务 COMPLETED。
- 抛异常 → 任务 FAILED，`f"handler error: {e}"` 回传（SDK 已 `logger.exception`）。
- 建议**自己 try/except** 把预期错误转成给人看的文本返回（如示例的 `[rejected] ...`），而不是抛异常。

## 注册 / 心跳 / 注销的 wire 行为

`RegistrationClient`（所有 httpx 调用 `trust_env=False` 绕开系统代理）：

- **注册** `POST {platform}/agent_platform/a2a/agents/register`
  body `{name, url(=public_url), owner, description, register_key, tc_agent_name, workdir}`。
  `workdir = os.getcwd()`（0.7.0 起自动携带，平台监控页展示工作目录；重注册即刷新）。
  成功（HTTP200 且 `status.code==0`）→ 存 `result.agent_token`（心跳/注销/shutdown 端点鉴权
  凭证，仅此一次返回）。
- **心跳** `POST .../agents/heartbeat`，头 `X-Agent-Token`；0.5.0 起 body 带
  `{busy, current_task_id, current_skill_id}`（executor 真实工作状态，平台据此续租 TC 锁/
  判空占）。收 401 → 清 token → 下轮自动重注册。
- **410（register 或 heartbeat）**：平台已删除/踢出本 agent → 停心跳/重注册并触发
  `on_platform_deleted`（默认退进程）。与 401 语义相反，**不会自动重连**。
- **`POST /_pyauto/shutdown`**（agent 侧控制端点，0.4.0 起）：平台删除时主动调用，
  `X-Agent-Token` 比对通过 → 先回 200 再延迟触发 `on_platform_deleted`。
- **注销** `POST .../agents/unregister`，头 `X-Agent-Token`（进程退出时尽力调用）。
- **`X-Computer-Token` 头**（0.6.0 起）：环境变量 `PYAUTO_COMPUTER_TOKEN` 非空（pyauto-computer
  CLI 拉起 agent 时注入）则 register/heartbeat 自动携带，平台据此关联 `a2a_agent.computer_id`。
- **重试**：注册失败指数退避 5→10→…→120s；启动先 `wait(2s)` 等 uvicorn 起监听（平台注册即回抓 card）。

## AgentCard 生成

`build_card()` 产出 A2A v1.0 `AgentCard`：`capabilities=AgentCapabilities(streaming=False)`，
`supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=public_url, protocol_version="1.0")]`，
`default_input_modes/output_modes=["text/plain"]`，skills 由 `@app.skill` 累积。
card 发布在 `<public_url>/.well-known/agent-card.json`（v1.0 拼写，注意不是旧版 `agent.json`）。

## 平台消费侧 REST（查询 agent / 轮询派发结果）

以上都是 agent 侧端点；从调用方（pi / 脚本）直连平台排查派发时用这组 REST，均需
`Authorization: Bearer <用户 JWT>`（平台登录态，pi 本地存于 `~/.pi/agent/a2a-mentions.json`
的 `baseUrl`/`token`/`expiresAt`；curl 访问 192.168.2.13 记得 `--noproxy`）：

| 端点 | 返回 |
|---|---|
| `GET /agent_platform/a2a/agents` | `result.data[]`：全部 agent（id/name/agent_type/status/url/busy） |
| `GET /agent_platform/a2a/dispatches/<id>` | `result`：`state`（`working`/`completed`/`failed`）+ `result_text`/`error` + `remote_task_id` |

- **派发创建响应**：`POST /dispatch` 返回 `{"dispatches":[{"dispatch_id":N,"agent_id":...,"agent_name":...}]}`。
  `dispatch_id` 出现在 `dispatches` 数组里即代表**服务端已创建派发**——客户端解析失败
  （如 pi `a2a_send` 报「没有 dispatch id」）不影响执行，拿 id 轮询上面的 dispatches 端点即可拿结果。
- **`state=working` 的两种常态**：① 平台已转 30s 轮询 `GetTask`（见上节）；② handler 仍在阻塞
  执行——例如 agent 在目标机弹出模态 GUI 对话框时，用户点掉弹框前派发一直停在 working。

## TaskState 与结果回传

executor 用 `TaskUpdater` 驱动：`TASK_STATE_WORKING`（收到即置）→ `add_artifact(text)` → `TASK_STATE_COMPLETED`；
出错置 `TASK_STATE_FAILED`。平台侧 `run_dispatch` 阻塞 `SendMessage`：拿到终态 Task 直接落结果；
拿到非终态则记 `remote_task_id` 转 working，由 30s 轮询 `GetTask` 收尾（`cancel` 当前 SDK 未实现，
派发取消对代理 agent 是尽力而为）。
