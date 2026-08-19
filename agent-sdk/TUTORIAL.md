# pyAutomation Agent 开发教程

在自己电脑（或任意内网机器）上发布一个 A2A 协议 agent，接入 pyAutomation Agent 平台，
接受平台派发的任务（类似 TeamCity / Jenkins 的 build agent）。

## 1. 环境要求

- Python **>= 3.10**
- 内网可访问 pyAutomation 平台（默认 `http://<server>:5000`）
- 本机开放一个端口供平台回连（agent 就是一个 A2A HTTP 服务）

## 2. 安装（uv）

示例 agent 的运行环境放在 `examples/`，自带 `pyproject.toml`（依赖 `pyauto-agent` 指向上级
源码路径），在该目录下直接 `uv sync` 即可，不需要额外参数：

```bash
cd pyAutomation/agent_sdk/examples
uv sync
# 装好 a2a-sdk[http-server]、uvicorn、httpx 等依赖，.venv 生成在 examples/ 本地
```

自己新建一个 agent 项目时同理：在你的 agent 目录下写一份 `pyproject.toml`，依赖里加
`pyauto-agent`，用 `[tool.uv.sources]` 的 `path` 指向 `agent_sdk` 目录（本地开发联调）或
`index`（内网发布索引，见 `references/patterns.md`「部署」一节），然后 `uv sync`。

## 3. 20 行写一个 agent

```python
from pyauto_agent import AgentApp

app = AgentApp(
    name="daisy-pc-agent",                    # 平台全局唯一，@名 派发用
    description="Daisy 工作机上的任务 agent",
    platform_url="http://pyauto-server:5000", # 平台地址
    public_url="http://10.20.30.40:9000",     # 本机对内网可达的地址+端口
    owner="daisy",
    register_key="",                          # 平台配置了注册密钥时填写
)

@app.skill(id="run_build", name="Run Build", tags=["build", "local"])
def run_build(text: str) -> str:              # 同步函数，SDK 在线程中执行
    # ... 干活 ...
    return "build ok"

app.run(host="0.0.0.0", port=9000)            # 阻塞运行
```

`app.run()` 会同时做三件事：

1. 以 Starlette + uvicorn 启动 A2A 服务（agent card 发布在
   `<public_url>/.well-known/agent-card.json`）
2. 后台线程向平台 `POST /agent_platform/a2a/agents/register` 注册
   （平台会回抓 card 探活；失败自动指数退避重试）
3. 每 30s 心跳一次；进程退出时尽力 unregister，平台立即显示离线
   （异常退出/断网时平台最迟约 3 分钟感知离线）

## 4. 多 skill 与消息路由

一个 agent 可注册多个 skill。派发消息以 `<skill_id>:` 前缀路由：

- `"run_cmd: system_info"` → 路由到 id 为 `run_cmd` 的 skill，参数是 `system_info`
- 无前缀 → 交给**第一个**注册的 skill（默认 skill）

## 5. 运行示例 agent

在 `examples/` 目录里（已 `uv sync` 过）：

```bash
cd examples

# Echo 示例（最小连通性验证）
uv run python hello_agent.py

# 本地命令执行示例（先编辑 command_whitelist.json）
uv run python command_runner_agent.py

# 转发给本机 pi CLI（大模型）问答的示例
uv run python pi_relay_agent.py
```

环境变量可覆盖默认值：`PYAUTO_PLATFORM_URL`、`PYAUTO_AGENT_PUBLIC_URL`、
`PYAUTO_AGENT_NAME`、`PYAUTO_AGENT_OWNER`、`PYAUTO_REGISTER_KEY`。

### command_runner 安全模型

- 只执行 `command_whitelist.json` 中 **别名 → 固定 argv** 的命令，
  不拼接、不解释任意 shell 字符串
- 白名单由 agent 所有者本人维护并自行负责
- 每条命令默认 300s 超时，输出截断 20000 字符后回传

## 6. 从平台派发任务

- 前端「Agent 平台监控」页可查看在线状态并发起派发
- API 方式：

```bash
# 按名称派发（@名 场景）
curl -X POST http://pyauto-server:5000/agent_platform/a2a/dispatch \
  -H "Authorization: Bearer <你的JWT>" -H "Content-Type: application/json" \
  -d '{"agent_name": "daisy-pc-agent", "message": "run_cmd: system_info"}'

# 按 skill tag 广播给所有在线匹配 agent
curl -X POST http://pyauto-server:5000/agent_platform/a2a/dispatch \
  -H "Authorization: Bearer <你的JWT>" -H "Content-Type: application/json" \
  -d '{"skill_tag": "build", "message": "nightly build", "broadcast": true}'
```

返回 `dispatch_id` 后可轮询 `GET /agent_platform/a2a/dispatches/<id>`，
或用 SSE `GET /agent_platform/a2a/dispatches/<id>/stream` 实时拿状态。

## 7. 常见问题

| 现象 | 原因 / 处理 |
|------|------------|
| 注册一直重试失败 | 平台回抓不到你的 card：检查 `public_url` 是否内网可达、**Windows 防火墙**是否放行该端口 |
| register rejected: invalid register_key | 平台配置了 `AGENT_PLATFORM_REGISTER_KEY`，启动时传入 `register_key` |
| 名称冲突 already registered with a different url | agent name 全平台唯一；换名字，或在原机器上用同一 url 重新注册 |
| 平台显示 offline 但 agent 还活着 | 心跳不通（网络/平台重启）；SDK 会自动重注册，恢复后 ~1 分钟内转 online |
| 派发一直 working | agent handler 卡住；平台轮询约 20 分钟后置 timeout |

## 8. 云端 agent

任何常驻内网服务器的进程用法完全相同——`public_url` 填服务器地址即可；
也可以不用本 SDK，直接用官方 `a2a-sdk` 起一个标准 A2A 服务
（参考 `a2a-samples/samples/python/agents/helloworld/`），
再自行调用平台的 register / heartbeat 接口。
