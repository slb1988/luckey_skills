# 不用 pyauto_agent：原生 a2a-sdk 手写代理 agent

适用：非 Python 语言、已有 A2A 服务、或需要 streaming/长任务 Task 跟踪等 SDK v1 未封装的能力。
核心：**任何符合 A2A v1.0 的 HTTP 服务 + 主动调用平台注册/心跳接口**，即可成为代理 agent。

参考样例：`a2a-samples/samples/python/agents/helloworld/`（1.1.0 API，与平台对齐）。

## 一、起一个 A2A v1.0 服务（Python + a2a-sdk 1.1.0）

```python
import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState
from a2a.helpers import get_message_text, new_task_from_user_message, new_text_message, new_text_part
from starlette.applications import Starlette

PUBLIC_URL = "http://10.20.30.40:9000"

class MyExecutor(AgentExecutor):
    async def execute(self, ctx: RequestContext, q: EventQueue):
        task = ctx.current_task or new_task_from_user_message(ctx.message)
        if not ctx.current_task:
            await q.enqueue_event(task)
        up = TaskUpdater(event_queue=q, task_id=task.id, context_id=task.context_id)
        await up.update_status(state=TaskState.TASK_STATE_WORKING, message=new_text_message("working"))
        result = do_work(get_message_text(ctx.message) or "")
        await up.add_artifact(parts=[new_text_part(text=result, media_type="text/plain")])
        await up.update_status(state=TaskState.TASK_STATE_COMPLETED, message=new_text_message("done"))
    async def cancel(self, ctx, q):
        raise NotImplementedError

card = AgentCard(
    name="my-agent", description="…", version="0.1.0",
    default_input_modes=["text/plain"], default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=False),
    supported_interfaces=[AgentInterface(protocol_binding="JSONRPC", url=PUBLIC_URL, protocol_version="1.0")],
    skills=[AgentSkill(id="do", name="Do", description="…", input_modes=["text/plain"],
                       output_modes=["text/plain"], tags=["demo"], examples=["hi"])],
)
handler = DefaultRequestHandler(agent_executor=MyExecutor(), task_store=InMemoryTaskStore(), agent_card=card)
routes = [*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")]
uvicorn.run(Starlette(routes=routes), host="0.0.0.0", port=9000)
```

## 二、主动注册 + 心跳（另起一个线程/协程）

平台接口（HTTP，body/返回都是 `{status:{code,message}, result}` 信封）：

| 方法 | 路径 | 头/体 | 说明 |
|------|------|-------|------|
| POST | `/agent_platform/a2a/agents/register` | body `{name, url, owner, description, register_key}`；可选 `tc_agent_name`、`workdir`（监控页展示工作目录，建议上报进程 cwd） | 平台回抓 `<url>/.well-known/agent-card.json`；成功返回 `result.agent_token`（仅一次） |
| POST | `/agent_platform/a2a/agents/heartbeat` | 头 `X-Agent-Token`；可选 body `{busy, current_task_id, current_skill_id}` | 每 ~30s 一次；401 → 重注册；**410 → 已被平台删除，停连（重启进程即重注册回归）** |
| POST | `/agent_platform/a2a/agents/unregister` | 头 `X-Agent-Token` | 退出时调用 |
| POST | `/_pyauto/shutdown`（**本 agent 侧**端点，可选实现） | 头 `X-Agent-Token` | 平台删除时主动踢下线：验 token 回 2xx 并退出进程，平台即彻底删除记录；不实现则走 410 兑底 |

```python
import httpx
BASE = "http://pyauto-server:5000/agent_platform/a2a"
NP = {"trust_env": False}     # 必须：绕开系统代理，否则内网/回环被 Clash 等 502

r = httpx.post(f"{BASE}/agents/register", json={
    "name": "my-agent", "url": PUBLIC_URL, "owner": "me", "description": "…",
    "register_key": "", "workdir": os.getcwd(),
}, timeout=15, **NP)
token = r.json()["result"]["agent_token"]
# 循环：httpx.post(f"{BASE}/agents/heartbeat", headers={"X-Agent-Token": token}, timeout=10, **NP)
```

## 三、其它语言 / 现成 A2A 服务

只要你的服务：
1. 在 `<public_url>/.well-known/agent-card.json` 暴露 A2A v1.0 AgentCard；
2. 在 `/` 接受 JSON-RPC 2.0 的 `SendMessage`（PascalCase 方法名，参数 proto3 JSON 映射，
   枚举如 `TASK_STATE_COMPLETED`、`ROLE_USER`），**请求会带 `A2A-Version: 1.0` 头**，
   你的 handler 需接受该版本；
3. 用任意 HTTP 客户端调平台的 register/heartbeat/unregister（见上表）；

即可接入平台，与 pyauto_agent 写的 agent 完全等价。平台侧 wire 细节见
`backend/.../agent_platform/a2a/SKILL.md` 的「Wire 协议要点」。

## 注意

- **A2A-Version 头**：平台派发时带 `A2A-Version: 1.0`；v1.0 handler 缺该头会按 0.3 拒绝（error -32009）。
- **样例版本漂移**：a2a-samples 里不少 agent 针对 0.2/0.3 旧 API（`A2AStarletteApplication`、
  `A2AClient`、小写 TaskState），与本地装的 1.1.0 不兼容。以 `helloworld` + 本文档为准。
