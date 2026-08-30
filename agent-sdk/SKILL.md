---
name: agent-sdk
title: 代理 Agent 开发指南（pyAutomation Agent 平台）
description: 开发接入 pyAutomation Agent 平台的「代理 agent（proxy agent）」的权威参考——跑在用户电脑/云服务器上、通过 HTTP 接收平台派发任务的 A2A agent。当需要新建一个代理 agent、用 pyauto_agent SDK（AgentApp/@app.skill）写 agent、让构建机上的 agent 与 TeamCity 构建互斥（tc_agent_name / workspace 锁）、或发布 SDK 新版本到内网 PyPI 时使用本 skill。SDK 只在本工程（pyAutomation/agent-sdk/）内开发和发布；其他工程/机器只是使用方，从内网 PyPI 装包即可。
tags: [A2A, ProxyAgent, AgentSDK, Pyauto-Agent, Python, TeamCity-Lock]
---

# 代理 Agent 开发指南

代理 agent = 跑在用户电脑/构建机上的独立 A2A HTTP 服务，平台经 JSON-RPC 派发任务、
靠 30s 心跳判存活（平台机制详见 `backend/.../agent_platform/a2a/SKILL.md`）。
**SDK（`pyauto-agent`）只在本目录开发、构建、发布；使用方任何工程直接从内网 PyPI 安装。**

## 最小可用示例

```python
from pyauto_agent import AgentApp

app = AgentApp(
    name="daisy-pc-agent",                     # 平台全局唯一，@名派发用
    description="Daisy 工作机上的任务 agent",
    platform_url="http://192.168.2.13:5000",   # 内网生产平台地址（默认值即此）
    public_url="http://10.20.30.40:9000",      # 本机内网可达地址+端口（平台会回抓）
    owner="daisy",
    # tc_agent_name="WinBuilder3",             # 仅当 agent 跑在 TC 构建机上：启用 workspace 互斥锁
)

@app.skill(id="run_build", name="Run Build", tags=["build", "local"])
def run_build(text: str) -> str:               # 同步函数，SDK 在线程里执行
    return do_work(text)

app.run(host="0.0.0.0", port=9000)             # 阻塞：起服务 + 后台注册/心跳
```

## 核心契约（写新 agent 必须知道的）

1. **handler 是同步函数 `(text: str) -> str`**，在线程执行可放心阻塞 IO；返回字符串即任务
   结果，抛异常 → FAILED。
2. **路由 `"<skill_id>: 参数"`**：前缀命中已注册 skill id 则分流，否则整条给第一个 skill。
3. **存活**：注册即 online，30s 心跳（成功静音、不产生日志），断连最迟 ~3 分钟判离线；
   被平台删除即退出进程，重启即重新注册回归。
4. **安全**：agent 以你的权限跑在你的机器上，**绝不 `eval`/`shell=True` 拼接** 派发文本；
   跑命令用白名单（见 `examples/command_runner_agent.py`）。
5. **`public_url` 必须平台可达**（内网 IP，非 127.0.0.1，放行防火墙），name 全局唯一，
   长任务注意平台派发 600s 超时。

## SDK 版本能力速览

| 版本 | 主要能力 |
|------|----------|
| 0.9.0 | A2A 图片附件按 metadata 引用回拉到 `.pyauto/inbox/<task_id>/`，handler 收到本机路径清单；下载/编码/大小校验失败直接置 FAILED；保存时清理 7 天前的 task 目录。 |
| 0.8.0 | 侧线 skill（`side=True`）、可取消底层进程、结果投递失败信息加固。 |
| 0.7.0 | 注册时上报 agent 进程工作目录。 |
| 0.6.0 | `X-Computer-Token` 受管计算机关联。 |
| 0.5.0 | TeamCity workspace 互斥锁与 busy 心跳。 |

## 图片附件回拉（0.9.0 起）

平台可在 A2A `message.metadata.pyauto_attachments` 中携带附件描述。SDK 使用 agent
自己持有的 `platform_url` 与注册后签发的 `agent_token` 回拉二进制，将文件安全保存到
`<cwd>/.pyauto/inbox/<task_id>/<basename>`，并把中文附件清单追加给原有 `(text: str) -> str`
handler；handler 签名不变。回拉使用 `X-Agent-Token`、60s 超时且 `trust_env=False`。

附件 `content_encoding` 目前只接受 `identity`；下载网络错误、非 200、声明大小与实际内容
不符或未知编码都会让任务 FAILED，不会在缺附件时继续执行。文件名会 basename 化并净化，
重名自动加 `_2`、`_3` 后缀。每次成功保存新附件时，SDK 顺带删除 inbox 下 mtime 超过
7 天的旧 task 目录。

## 工作目录上报（workdir，0.7.0 起）

注册 body 自动携带 `workdir = os.getcwd()`（pyauto-computer 受管 agent 的 cwd 即
workroot），平台写入 `a2a_agent.workdir`，监控页「受管计算机 → Agent 数 → 详情」
展示；重注册自动刷新。裸 SDK 无需任何改动——cwd 即其工作目录，同样受益。

## 侧线 skill 与取消（0.8.0 起）

- **`@app.skill(..., side=True)`**：侧线 skill（如 pyauto-computer host 内置的 `btw`
  进度查询）——轻量只读查询专用：**不参与 busy 记账**（心跳仍报主任务，side 任务
  不会把 `current_task_id` 冲掉导致平台误判主任务丢失）、**不取 workspace 锁**
  （主任务持锁期间 side 查询也能进来）。写「长任务执行中查询/探测」类 skill 必须
  加 side=True，否则 busy 状态机会被并发查询打乱。
- **cancel 真正实现**：`executor.cancel()` 不再抛 NotImplementedError（a2a-sdk 的
  on_cancel_task 先调 executor.cancel 再杀 producer，抛异常会让取消链路整体失效）。
  现行为：先上报 CANCELED 终态（**顺序敏感**：先标记再杀进程，否则 handler 抢先
  完成会关掉事件队列导致 CANCELED 被丢弃、任务永远卡 WORKING），再调
  `AgentApp(on_cancel=...)` 回调杀底层子进程（host 传 runtime 适配器的
  cancel_current，杀整棵进程树）。
- **结果投递加固**：handler 跑完后的 add_artifact/update_status 异常不再被框架层
  静默置 FAILED（曾导致平台收到无任何文本的失败任务、结果全丢）——兜底改为带
  异常信息 + handler 输出摘要的 FAILED。
- `_BusyState` 新增 payload 摘要 + started_at，`app.busy_state.current_run_info()`
  供本机侧线 skill 读「正在跑什么/跑了多久」（不进心跳 body）。

## pyauto-computer 机群关联（X-Computer-Token，0.6.0 起）

`pyauto-computer` CLI（`pyAutomation/computer-cli/`，Raft 式受管计算机）拉起 agent 进程时
注入 `PYAUTO_COMPUTER_TOKEN` 环境变量；SDK 的 register/heartbeat 自动带
`X-Computer-Token` 头，平台据此把 agent 关联到所属 computer（`a2a_agent.computer_id`，
监控页「受管计算机」卡片可见各机 agent 数）。裸 SDK 不设该环境变量行为完全不变。

## TeamCity 构建机互斥（tc_agent_name，0.5.0 起）

agent 跑在 TC 构建机上、会动 P4 workspace 时，给 `AgentApp` 传 `tc_agent_name="<TC agent 名>"`：

- **每个任务执行前 SDK 强制经平台获取该构建机的 workspace 锁**：平台先禁用 TC agent
  （新构建排队）→ 等在跑构建排空 → 才执行 handler；执行完自动释放恢复接单。
  等锁上限 `lock_acquire_timeout`（默认 3600s），拿不到任务置 FAILED。handler 里零锁代码。
- 心跳自动上报 busy 状态：平台据此续租；空占（持锁但持续不干活超 5min）/进程崩溃/离线
  都会被服务端自动回收（TTL → sweeper → TC statusSwitchTime 三重兜底），不会锁死构建机。
- 独立脚本（不起 AgentApp）用底层 helper：
  ```python
  from pyauto_agent import teamcity_workspace_lock
  with teamcity_workspace_lock(agent_name="WinBuilder3", owner="my-script",
                               reason="manual p4 sync", auto_renew=True):
      ...
  ```
- 完整示例：`examples/workspace_lock_example.py`；服务端实现：
  `backend/server/applications/teamcity/lock_helper.py`（接口 `/teamcity/agent_lock/*`）。

## 安装（使用方，从内网 PyPI）

```bash
# uv 项目：patterns 模板里的 [[tool.uv.index]] pl-internal 配置（explicit=true）
# 裸 pip：
pip install --index-url http://192.168.2.13:8080/simple/ --trusted-host 192.168.2.13 pyauto-agent
```

环境统一用 uv（`uv sync` 建 `.venv`），不要 `path` 指向本目录源码（那只用于本地改 SDK 联调）。
agent 目录模板/冒烟步骤见 [patterns](references/patterns.md#部署)。

## 发布新版本（仅在本工程执行）

pypiserver 宿主 `192.168.2.13`（包存储 `/home/dev/pypi-server/packages/`，
`systemctl --user status|restart pypi-server`）：

1. **升版本号**：改 `pyproject.toml` 的 `version`（先 `p4 edit`）——`__version__`
   从包元数据读取（0.8.0 起），不用改第二处。同版本重传会被 pypiserver 拒绝——
   最常见的发布失败原因。
2. **临时目录构建**（P4 只读目录里直接 build 会产生 `dist/`、`*.egg-info` 污染）：
   把 `pyproject.toml` + `pyauto_agent/` 复制到 scratchpad，`uv build --out-dir dist`。
3. **上传**（认证 `admin / sdk123456`；务必绕过系统代理）：
   ```bash
   NO_PROXY=192.168.2.13 uvx twine upload --repository-url http://192.168.2.13:8080 \
       --username admin --password sdk123456 dist/*
   ```
4. **验证**：`curl --noproxy 192.168.2.13 http://192.168.2.13:8080/simple/pyauto-agent/` 列出新版本。
5. 版本号与源码改动走正常 P4 流程提交。

## 深入参考（按需查阅，正文不再展开）

- [troubleshooting](references/troubleshooting.md) — 注册/心跳/代理 502/删除复活/锁排障/Windows subprocess 坑
- [api-reference](references/api-reference.md) — `AgentApp` / `@app.skill` / `run()` 全参数、wire 行为
- [patterns](references/patterns.md) — 完整示例、安全白名单、多 skill、部署模板与冒烟
- [raw-a2a-sdk](references/raw-a2a-sdk.md) — 不用本 SDK、原生 a2a-sdk 手写代理 agent
- `TUTORIAL.md` — 面向使用者的中文上手教程
- `examples/` — `hello_agent.py` / `command_runner_agent.py` / `pi_relay_agent.py` /
  `workspace_lock_example.py`（`cd examples && uv sync` 即可跑）
