---
name: agent-sdk
title: 代理 Agent 开发指南（pyAutomation Agent 平台）
description: 开发/调试接入 pyAutomation Agent 平台的「代理 agent」（跑在用户机器上、HTTP 接收平台派发的 A2A agent）的权威参考。新建代理 agent、pyauto-computer 受管接入、pyauto_agent SDK 手写、排查注册/心跳/派发问题时必读。
tags: [A2A, ProxyAgent, AgentSDK, Pyauto-Agent, Pyauto-Computer, Python]
---

# 代理 Agent 开发指南

**何时使用本 skill**：凡是要「让平台调用某台机器去干活」「操控本地电脑做事」「加一个
build/命令/采集类 agent」都先读这里。具体场景：新建/实现/调试代理 agent；用 `pyauto_agent`
SDK（`AgentApp`/`@app.skill`）写 agent；新机零代码接入（pyauto-computer 受管模式：
install.ps1 / setup / agent create / 开机自启）；排查注册失败、心跳掉线、派发不通；不便用
SDK 时用原生 a2a-sdk 手写代理 agent。

平台有三类 agent（详见 `backend/.../agent_platform/a2a/SKILL.md`）：

| | 代理 agent（本 skill） | 云 agent | 本地 agent |
|---|---|---|---|
| 载体 | 用户电脑/云服务器上的独立 A2A HTTP 服务 | 无端点，服务端调 LLM | 服务端存盘目录代码 |
| 适用 | 操控本机、跑命令/构建、采集本机信息、访问内网资源 | 纯 prompt 推理 | 高权限服务端执行体 |
| 派发 | 平台 HTTP JSON-RPC `SendMessage` | 服务端 `run_cloud_llm` | 进程内执行 |
| 存活 | 注册 + 30s 心跳 + 离线扫描 | 恒 online | 恒 online（目录消失置 offline） |

**新建代理 agent 有两条路径**：① 需求只是「让这台机器能收派发、用本机 coding-agent CLI
干活」→ 首选 **pyauto-computer 受管模式**（零代码，见下节）；② 需要自定义 skill 集（白名单
命令、双 lane 队列、下载端口、自有 prompt 模板）→ 用 **`pyauto_agent` SDK** 手写，即本 skill 主体。

**手写代理 agent 用 `pyauto_agent` SDK**（唯一开发/发布地：`pyAutomation/agent-sdk/`，本目录
是同步镜像、只读参考，**不要在这里改代码**）：封装了 AgentCard 构建、Starlette/uvicorn 服务、
自动注册 + 心跳 + 退出注销。人类向导见 `TUTORIAL.md`；本 skill 面向实现/调试。
不便用 SDK 时（非 Python、已有 A2A 服务）见 [raw-a2a-sdk](references/raw-a2a-sdk.md)。

机群化已落地（pyauto-computer，对标 Raft 接入体验）：① 平台托管 install.sh/ps1 一行装 CLI；
② Computer 一等实体：`setup` 登记（hostname+机器指纹+OS+探测 runtime）即签发 computer_token
（内网开放，无审批环节）；③ 一机多 agent：每 agent 独立目录（=runtime cwd）+独立端口
（9100-9299 自动分配）+独立日志，create 前过服务端名字预校验；④ runtime 适配器
（pi/claude/codex/kimi/opencode）。**让一台机器接入平台跑 agent，优先走
`pyauto-computer` CLI（`pyAutomation/computer-cli/`，README 是用户向文档），不要手写 agent 进程**；
只有 CLI 模型不满足（自定义 skill 路由、特殊执行体）才裸用 SDK。
受管 agent 要加自定义逻辑：workroot 放 `agent_ext.py`（`register(app)` 挂 skill，同一 SDK API），
`agent create --ext` 出骨架，`agent dev <名> [消息]` 本地调试（不注册平台，可打断点）。

## 受管模式 pyauto-computer（零代码接入）

平台托管的 CLI 把 AgentApp + runtime 适配（pi/claude/codex 等）+ 注册/心跳 + 进程守护全包掉：

```powershell
irm http://192.168.2.13/pyauto-computer/install.ps1 | iex   # 装 CLI（wheel 平台自托管，:8080 挂了也能装）
pyauto-computer setup                                        # 指纹登记本机（幂等），探测 runtime
cd <工作目录>; pyauto-computer agent create <名> --autostart  # workroot=cwd，只写一个 .pyauto/
pyauto-computer agent start <名>                             # 拉起 host，注册上线
pyauto-computer service install                              # 一条 OS 自启项拉起 supervisor 守护全部 agent
```

在库实例：winbuilder3-maindev（端口 9100，workroot=MainDev 仓库根）、nas@QNAP NAS453Dmini
（端口 9100，跨网段经 10.77.77.4 访问平台，接入要点见 pyauto-computer 参考「跨网段/受限网络接入」）。
平台默认地址 192.168.2.13 不可达的机器：装 CLI 要 sed 替换脚本内嵌 IP，且
`PYAUTO_PLATFORM_URL` 必须写进 shell profile 长期生效（agent 子命令不读 computer.json）。
> 详细参考（目录语义/端口段/自启模型/A2A 手测报文）：[pyauto-computer](references/pyauto-computer.md)

**「升级/更新本地 agent 并重启 <名>」= 固定四步，直接照做，出问题再排查，不要过度设计**：

```bash
pyauto-computer agent stop <名>                                  # 1. 停（立即上报 offline）
powershell -NoProfile -Command "irm http://192.168.2.13/pyauto-computer/install.ps1 | iex"  # 2. 装平台托管最新 wheel（幂等）
pyauto-computer agent start <名>                                 # 3. 起
pyauto-computer agent logs <名> | tail -15                       # 4. 验证：看到 `registered: agent_id=` 即上线
```

说明：install.ps1 一条同时刷 `pyauto-computer` CLI 和它依赖的 `pyauto_agent`（agent host 跑在
CLI 的 uv tool 环境里，升 CLI 即升 SDK），`~/.pyauto` 状态与 agent 映射不动。可选前置检查：
`pyauto-computer version` 对比 `curl --noproxy 192.168.2.13 http://192.168.2.13:5000/agent_platform/a2a/computer/packages`
列出的版本；install.ps1 本身幂等，跳过对比直接跑也行。

## 最小可用示例

```python
from pyauto_agent import AgentApp

app = AgentApp(
    name="daisy-pc-agent",                     # 平台全局唯一，@名派发用
    description="Daisy 工作机上的任务 agent",
    platform_url="http://192.168.2.13:5000",   # 内网生产平台地址（本地调试才换 127.0.0.1）
    public_url="http://10.20.30.40:9000",      # 本机内网可达地址+端口（平台会回抓）
    owner="daisy",
    register_key="",                           # 平台配了 AGENT_PLATFORM_REGISTER_KEY 才填
)

@app.skill(id="run_build", name="Run Build", tags=["build", "local"])
def run_build(text: str) -> str:               # 同步函数，SDK 在线程里执行
    return do_work(text)

app.run(host="0.0.0.0", port=9000)             # 阻塞：起服务 + 后台注册/心跳
```

`app.run()` 同时做三件事：① uvicorn 起 A2A 服务，card 发布在 `<public_url>/.well-known/agent-card.json`；
② 后台线程注册到平台（失败指数退避重试）；③ 每 30s 心跳，进程退出时注销。

## 核心契约（实现新 agent 必须理解）

**1. skill handler 是同步函数 `(text: str) -> str`。** 返回的字符串作为任务结果（artifact）回传平台。
在独立线程里执行（`asyncio.to_thread`），所以可以放心做阻塞 IO（subprocess、文件、网络）。
抛异常 → 任务置 FAILED，异常信息回传；正常返回 → COMPLETED。

**2. 消息路由：`"<skill_id>: 参数"`。** 一个 agent 可注册多个 skill。平台派发的消息若以
`run_cmd: xxx` 开头且 `run_cmd` 是已注册 skill id，则路由到它、`xxx` 作为 `text`；否则整条消息
交给**第一个注册的 skill**（默认 skill）。所以单 skill agent 直接收原文，多 skill 用前缀分流。

**3. 生命周期与存活。** 注册即 online；每 30s 心跳刷新平台 Redis TTL(120s)。掉线判定：
心跳断 → 平台离线扫描最迟 ~3 分钟置 offline（pyauto-computer 受管机另有 CLI inventory 上报，
进程死**立即** offline）；派发连接失败 → 立即 offline。心跳 401（token 轮换）→ 自动重注册。

**4. 删除语义（被平台踢下线）。** admin 在监控页删除 → 平台先主动调 agent 的
`POST /_pyauto/shutdown`（0.4.0+，token 鉴权）——杀到即彻底删除，SDK 默认回调**直接退进程**；
杀不到留 tombstone（`status=deleted`，对所有列表不可见），agent 下次心跳撞 **410** 后退进程。
重新注册即复活（无需管理员操作），所以删除踢掉的只是"当前挂着的那个进程"。

**5. 平台如何找到并调用你的 agent。** 前端/`POST /dispatch` 支持三种目标：`agent_id`、`agent_name`
（@名）、`skill_tag`（按 card 里的 skill tags 匹配，可广播给所有在线匹配 agent）。所以 skill 的
`tags` 直接决定能否被 skill_tag/广播命中——给 skill 起有意义的 tag。

## 开发新代理 agent 的检查清单

1. **想清楚 skill 边界**：一个 agent 做一类事；多能力用多个 `@app.skill`，靠 `id` 前缀分流。
2. **handler 只做该做的**：解析 `text` → 干活 → 返回**给人看的文本结果**（平台/前端直接展示）。
3. **安全**：agent 跑在你自己机器上、以你的权限执行。**绝不 `eval`/直接 `shell=True` 拼接** `text`。
   需要跑命令就用**白名单**（见 `examples/command_runner_agent.py`：别名→固定 argv + 超时 + 输出截断）。
4. **`public_url` 必须平台可达**：填内网 IP（非 `127.0.0.1`，除非平台同机），**放行防火墙端口**。
5. **name 全局唯一**：与已注册 agent 同名不同 url 会被平台拒绝（deleted tombstone 同名可接管复活）。
6. **超时与体积**：长任务注意 handler 会阻塞该次派发的 HTTP（平台默认 600s 超时）；大输出先截断再返回。
7. **环境用 uv，不裸 `pip install`**：agent 目录自带 `pyproject.toml`（依赖 `pyauto-agent`，**首选
   内网 PyPI 索引**安装，见下方「SDK 安装与发布」；只有在本地改 SDK 源码联调时才用 `path` source
   指向 `pyAutomation/agent-sdk/`），`uv sync` 建 `.venv`，`uv run python your_agent.py` 跑。模板与
   README 固定骨架见 [patterns「新 agent 目录模板」](references/patterns.md#部署)。
8. **每次新建 agent / 运行已有 agent 前，主动把 SDK 更到最新**：不要沿用环境里的旧版。查内网源
   最新版本（`curl --noproxy 192.168.2.13 http://192.168.2.13:8080/simple/pyauto-agent/`），再升级：
   uv 项目 `uv sync -U`；裸 pip 见下方命令。新建 agent 的 `pyproject.toml` 固定版本号写成当前最新。
9. **本地冒烟**：起平台 → 起 agent → 前端「Agent 平台监控」看到 online → 派发 → 看结果。见 [patterns](references/patterns.md#冒烟测试)。

## SDK 版本能力速览

| 版本 | 能力 |
|---|---|
| 0.3.0 | 被平台删除（410）默认退进程；重启即重注册回归 |
| 0.4.0 | `POST /_pyauto/shutdown` 平台主动踢下线端点（删除单击生效的前提） |
| 0.5.0 | `tc_agent_name` 绑定 TC 构建机 + workspace 互斥锁；心跳 body 上报 busy/current_task_id |
| 0.6.0 | `PYAUTO_COMPUTER_TOKEN` 环境变量 → register/heartbeat 带 `X-Computer-Token`，关联所属 computer |
| 0.7.0 | 注册 body 自动携带 `workdir = os.getcwd()`（监控页详情展示工作目录；重注册即刷新） |
| 0.8.0 | side skill（`@app.skill(side=True)`：不占 busy/不取锁，长任务中的侧线查询如内置 `btw` 进度查询）；cancel 真正实现（先标 CANCELED 再调 `on_cancel` 杀进程树）；结果投递加固；`__version__` 改读包元数据 |

## 内网生产环境速查

`192.168.2.13` 一台宿主同时承载平台与包源：

| 服务 | 地址 | 用途 |
|---|---|---|
| pyAutomation 平台 | `http://192.168.2.13:5000` | 注册/心跳/派发；代码里 `platform_url` 的**默认值** |
| 内网 PyPI（pypiserver） | `http://192.168.2.13:8080/simple/` | 安装 `pyauto-agent`（见下节；**会挂**，挂了就走下节平台托管 wheel） |
| 平台托管 wheel | `http://192.168.2.13:5000/agent_platform/a2a/computer/packages` | `pyauto-agent` + `pyauto-computer` 当前版本 wheel 直链（install 脚本同源） |

**默认地址规则**：`platform_url` 默认 `http://192.168.2.13:5000`（本地调试用
`PYAUTO_PLATFORM_URL` 覆盖）。`public_url` 是本机内网地址（非 127.0.0.1、非 2.13），
默认用「UDP connect 取路由源地址」自动探测（实现见 `examples/` 的 `_local_ip()`）。

平台自身的前后端发布（「@auto-server 前后端更新发布」）不走 internal-tool-deploy 的
SFTP+systemd 套路：平台代码在 auto-server（192.168.2.13）上有自己的 P4 工作区，发布 =
服务器侧 `p4 sync` → 后端按 PID 重启 flask 进程（杀旧 PID、记新 PID，以 HTTP 200 为健康门；
发布前把 flask 日志归档进 `tmp/`、`app.log` 轮转为 `app.log.N`）→ 前端 `p4 sync` +
`vite build` 出 `dist`。后端业务模块在 `backend/server/applications/<app>/`（可各带自己的
SKILL.md），前端对应 `<module>.ts` + `<Module>.vue` 文件对。sync 时提示 "must resolve #N
before submitting" 的打开文件不阻塞本次发布，但会阻塞下一次提交——发布报告里要点名待
resolve 清单，提醒负责人先 resolve。

## SDK 安装与发布

**当前最新版 0.8.0**（2026-08；以内网源实时列表为准，别信本行快照）。新建 agent 环境一律优先
从内网源装，`path` source 只用于本地改 SDK 联调。

**安装/更新（下载不需要认证）**：运行 agent 前主动执行一次更新。

- uv 项目：用 patterns 模板里的 `[[tool.uv.index]] pl-internal` 配置（`explicit = true`）；更新 `uv sync -U`。
- 裸 pip（`-U` 同时覆盖首装与升级）：
  `pip install -U --index-url http://192.168.2.13:8080/simple/ --trusted-host 192.168.2.13 pyauto-agent`
- pypiserver 挂了的兜底：直接装平台托管 wheel
  `pip install -U http://192.168.2.13:5000/agent_platform/a2a/computer/packages/pyauto_agent-<ver>-py3-none-any.whl`
- 查最新版本号：`curl --noproxy 192.168.2.13 http://192.168.2.13:8080/simple/pyauto-agent/`

> **发布新版本**（SDK/CLI 源码改完后的版本号升级、构建、上传 pypiserver、同步平台托管 wheel）：见 [publishing](references/publishing.md)

**pyauto-computer CLI 自身的升级/卸载**：升级 = 重跑 install 一行命令（`uv tool install --force`
覆盖，`~/.pyauto` 状态不动）；卸载 = `uv tool uninstall pyauto-computer`（CLI 无自带 uninstall，
`service uninstall` 只是移除开机自启项）。

## 深入参考

- [troubleshooting](references/troubleshooting.md) — 注册失败/心跳掉线/代理 502/协议版本/Windows 进程坑
- [pyauto-computer](references/pyauto-computer.md) — 受管模式 CLI 详解：目录语义/端口段/自启模型/A2A 手测报文。
- [api-reference](references/api-reference.md) — `AgentApp` / `@app.skill` / `run()` 全参数、wire 行为、TaskState、消费侧 REST（agent 列表 / 派发结果轮询）。
- [patterns](references/patterns.md) — 带注释的完整示例、安全白名单、多 skill、长任务、部署与冒烟。
- [publishing](references/publishing.md) — SDK/CLI 发版流程：版本号、构建、twine 上传、平台托管 wheel 同步。
- [raw-a2a-sdk](references/raw-a2a-sdk.md) — 不用 pyauto_agent，用原生 a2a-sdk 手写代理 agent（含注册/心跳）。
- `TUTORIAL.md`（同目录）— 面向使用者的中文上手教程。
- `examples/`（自带独立 `pyproject.toml`，`cd examples && uv sync` 即可跑）：
  `hello_agent.py`（echo，最小连通）、`command_runner_agent.py`（白名单命令，操控本机范式）、
  `pi_relay_agent.py`（转发给本机 `pi` CLI，含 Windows `.cmd` 解析坑的修法）、
  `workspace_lock_example.py`（tc_agent_name + workspace 互斥锁用法）。
