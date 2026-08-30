# pyauto_agent API 参考

> 面向实现/调试代理 agent。SDK 源码：`pyauto_agent/{app,executor,registration}.py`。

## 目录
- [AgentApp](#agentapp)
- [@app.skill](#appskill)
- [app.run](#apprun)
- [消息路由与 handler 契约](#消息路由与-handler-契约)
- [图片附件回拉与落盘](#图片附件回拉与落盘)
- [注册 / 心跳 / 注销的 wire 行为](#注册--心跳--注销的-wire-行为)
- [AgentCard 生成](#agentcard-生成)
- [TaskState 与结果回传](#taskstate-与结果回传)

## AgentApp

`AgentApp(name, platform_url, public_url, description="", owner="", version="0.1.0", register_key="", heartbeat_interval=30.0, on_platform_deleted=None)`

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
| `on_platform_deleted` | 平台删除/踢出本 agent 时的无参回调，触发途径：心跳/注册收 HTTP 410，或平台主动调 `POST /_pyauto/shutdown`（≥0.4.0，删除即秒杀）。**0.3.0 起默认直接退出进程**（`os._exit(0)`，释放名字，重启即重新注册回归）；要被踢后进程继续跑（只脱离平台、HTTP 服务保留）传自定义回调如 `lambda: None`。0.2.0 的默认行为相反（不退进程）。回调抛异常只记日志。 |

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

## 图片附件回拉与落盘

SDK 0.9.0 起读取 A2A `message.metadata.pyauto_attachments`：

```json
[{"id":"uuid","name":"foo.png","mime_type":"image/png","size":125952,
  "content_encoding":"identity"}]
```

对每项请求
`GET {platform_url}/agent_platform/a2a/attachments/{id}/content`，携带
`X-Agent-Token: <注册响应签发的 agent_token>`。客户端固定 `trust_env=False`、超时 60s；
token 在任务执行时动态读取，因此 AgentApp 在注册完成前构造 ASGI/executor 不会固化空 token，
且无附件的纯文本任务完全不依赖注册时序。

文件落到 `<cwd>/.pyauto/inbox/<task_id>/<basename>`。文件名会同时按 `/`、`\\` basename
化并净化 Windows 危险字符/设备名；已有同名文件时依次使用 `_2`、`_3` 后缀，不覆盖。
成功保存首个附件后，顺带删除 `.pyauto/inbox/` 下 mtime 超过 7 天的旧 task 目录。

handler 签名仍是 `(text: str) -> str`，收到的字符串为原路由 payload 加两个换行及清单：

```text
【附件 1 个，已保存到本机，用 read 工具查看】
- .pyauto/inbox/<task_id>/foo.png (image/png, 123 KB)
```

目前只认识 `content_encoding="identity"`。未知编码、网络错误、非 HTTP 200、metadata
声明大小与响应字节数不一致、或本地落盘失败都会在调用 handler 前将任务置 FAILED；错误
信息包含附件 id，HTTP 失败同时包含状态码（网络未获得响应时标记 `HTTP 状态 unavailable`）。

## 注册 / 心跳 / 注销的 wire 行为

`RegistrationClient`（所有 httpx 调用 `trust_env=False` 绕开系统代理）：

- **注册** `POST {platform}/agent_platform/a2a/agents/register`
  body `{name, url(=public_url), owner, description, register_key}`。
  成功（HTTP200 且 `status.code==0`）→ 存 `result.agent_token`（心跳/注销凭证，仅此一次返回）。
- **心跳** `POST .../agents/heartbeat`，头 `X-Agent-Token`。收 401 → 清 token → 下轮自动重注册；
  收 **410**（平台已删除/踢出本 agent，SDK ≥0.2.0）→ 置 `deleted=True`、停守护线程、触发
  `on_deleted` 回调（AgentApp 默认回调 0.3.0 起 = 退出进程），**不再重连**。注册收 410 同样
  停止重试。回归 = 重启进程重新注册（平台侧软删，注册即复活）。
- **注销** `POST .../agents/unregister`，头 `X-Agent-Token`（进程退出时尽力调用；已被 410 踢出时跳过）。
- **被踢控制端点（SDK ≥0.4.0）**：本 agent 的 Starlette 应用额外暴露
  `POST <public_url>/_pyauto/shutdown`，鉴权 = 请求头 `X-Agent-Token` 等于注册时平台签发的
  agent_token（`hmac.compare_digest`，注册成功前一律 403）。平台管理员点删除时主动调用：
  校验通过 → `reg.halt()`（置 deleted、停心跳线程）→ 先回 200 `{"ok": true}` →
  `threading.Timer(0.2s)` 延迟触发 `on_platform_deleted`（默认 `os._exit(0)`，延迟是为了
  让响应先送达平台）。403 无任何副作用。
- **重试**：注册失败指数退避 5→10→…→120s；启动先 `wait(2s)` 等 uvicorn 起监听（平台注册即回抓 card）。

## AgentCard 生成

`build_card()` 产出 A2A v1.0 `AgentCard`：`capabilities=AgentCapabilities(streaming=False)`，
`supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=public_url, protocol_version="1.0")]`，
`default_input_modes/output_modes=["text/plain"]`，skills 由 `@app.skill` 累积。
card 发布在 `<public_url>/.well-known/agent-card.json`（v1.0 拼写，注意不是旧版 `agent.json`）。

## TaskState 与结果回传

executor 用 `TaskUpdater` 驱动：`TASK_STATE_WORKING`（收到即置）→ `add_artifact(text)` → `TASK_STATE_COMPLETED`；
出错置 `TASK_STATE_FAILED`。平台侧 `run_dispatch` 阻塞 `SendMessage`：拿到终态 Task 直接落结果；
拿到非终态则记 `remote_task_id` 转 working，由 30s 轮询 `GetTask` 收尾（`cancel` 当前 SDK 未实现，
派发取消对代理 agent 是尽力而为）。
