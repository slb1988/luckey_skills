# 代理 Agent 实现范式

> 从「能跑」到「能上生产」的实践。配合 `examples/` 阅读。

## 目录
- [范式一：操控本机（白名单命令）](#范式一操控本机白名单命令)
- [范式二：多 skill 分流](#范式二多-skill-分流)
- [范式三：采集/只读信息](#范式三采集只读信息)
- [长任务与超时](#长任务与超时)
- [安全清单](#安全清单)
- [部署](#部署)
- [冒烟测试](#冒烟测试)

## 范式一：操控本机（白名单命令）

「让平台操控本地电脑做事」的标准安全写法——**只跑白名单里的固定命令，不解释任意输入**。
完整代码见 `examples/command_runner_agent.py`，要点：

```python
@app.skill(id="run_cmd", name="Run Whitelisted Command",
           tags=["shell", "local", "command"], examples=["list_dir", "run_cmd: system_info"])
def run_cmd(text: str) -> str:
    alias = text.strip()
    whitelist = _load_whitelist()          # {别名: [固定 argv]}，每次重读，改白名单免重启
    if alias not in whitelist:
        return f"[rejected] '{alias}' not in whitelist. Allowed: {', '.join(sorted(whitelist))}"
    proc = subprocess.run(whitelist[alias], capture_output=True, text=True, timeout=300)
    out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    return f"[exit code {proc.returncode}] {alias}\n{out[:20000]}"
```

关键：**别名 → 固定 argv 列表**（`subprocess.run(argv)` 不用 `shell=True`），超时兜底，输出截断。
白名单文件由 agent 所有者维护，加什么命令自己负责。

## 范式二：多 skill 分流

一个 agent 承载多种能力，靠 `id:` 前缀路由：

```python
@app.skill(id="build", name="Build", tags=["ci", "build"])      # 第一个=默认 skill
def build(text): ...        # 派发 "build: MainDev" 或（无前缀时）任意文本

@app.skill(id="clean", name="Clean Workspace", tags=["ci"])
def clean(text): ...        # 派发 "clean: /path"
```

派发 `"clean: D:/ws"` → `clean("D:/ws")`；派发 `"MainDev"`（无已知前缀）→ 默认 `build("MainDev")`。

## 范式三：采集/只读信息

无副作用、适合广播（`skill_tag` + broadcast 收集所有在线机器信息）。给稳定的 tag 便于批量命中：

```python
@app.skill(id="sysinfo", name="System Info", tags=["sysinfo", "readonly"])
def sysinfo(text: str) -> str:
    import platform, shutil
    total, used, free = shutil.disk_usage("/")
    return f"{platform.node()} | {platform.platform()} | disk free {free//2**30}GB"
```

## 长任务与超时

handler 会**阻塞该次派发的 HTTP 请求**，平台默认 `A2A_DISPATCH_TIMEOUT=600s`。若任务更久：
- 优先拆小、或让 handler 快速返回「已受理」并把真正的活丢到 agent 内部队列（本 SDK v1 不自动跟踪
  异步 Task 的后续状态，需要就走原生 a2a-sdk 的 streaming/Task 机制，见 raw-a2a-sdk）。
- 大输出（日志/文件内容）务必先截断（示例用 20000 字符）再返回，避免撑爆前端与 DB。

## 安全清单

- agent 以**你本人的系统权限**运行，能碰的它都能碰。只暴露你愿意让平台触发的能力。
- 永不 `eval(text)`、永不 `os.system(text)`/`subprocess.run(text, shell=True)` 拼接派发内容。
- 需要参数化命令 → 白名单别名或严格校验/转义参数。
- 生产给平台配 `AGENT_PLATFORM_REGISTER_KEY`，agent 侧 `register_key` 对齐，避免任意注册。
- `public_url` 只在**受信内网**暴露；agent 端口按需用防火墙限制来源 IP 为平台。

## 部署

- Python **>= 3.10**，用 **uv** 管理环境（不用裸 `pip install -e`）：每个新 agent 目录自带一份
  `pyproject.toml`，`uv sync` 建 `.venv` 并装好 `pyauto-agent` 及其依赖，`uv run python your_agent.py`
  跑。模板见下方「新 agent 目录模板」，实例见 `examples/pyproject.toml`（`agent-sdk/examples/` 自身
  就是这个模板的一份实例：`hello_agent.py`/`command_runner_agent.py`/`pi_relay_agent.py` 共享同一个
  `.venv`）。
- 后台常驻：Windows 用「计划任务/nssm 服务」，Linux 用 systemd/supervisor，启动命令用
  `uv run python your_agent.py`（不要手动激活 venv 再裸跑 `python`，`uv run` 会自动核对
  `pyproject.toml`/`.venv` 一致性）。
- 环境变量覆盖（示例 agent 已支持）：`PYAUTO_PLATFORM_URL`、`PYAUTO_AGENT_PUBLIC_URL`、
  `PYAUTO_AGENT_NAME`、`PYAUTO_AGENT_OWNER`、`PYAUTO_REGISTER_KEY`。
- 云 agent（服务器常驻进程）用法完全相同，`public_url` 填服务器地址即可。

### 新 agent 目录模板（`pyproject.toml` + README 骨架）

新建一个代理 agent 时，目录里除了 agent 脚本本身，固定带这两个文件：

```toml
# your-agent-dir/pyproject.toml
[project]
name = "your-agent-name"
version = "0.1.0"
description = "……"
requires-python = ">=3.10"
dependencies = [
    "pyauto-agent",
]

# 首选：内网 PyPI（pypiserver @ 192.168.2.13，pyauto-agent 已发布）
[[tool.uv.index]]
name = "pl-internal"
url = "http://192.168.2.13:8080/simple/"
explicit = true                      # 只对显式指定该 index 的包生效，其余依赖仍走默认 PyPI

[tool.uv.sources]
pyauto-agent = { index = "pl-internal" }

# 本地开发 SDK 本体时（改完 SDK 立即生效），把上面的 [tool.uv.sources] 换成：
# [tool.uv.sources]
# pyauto-agent = { path = "相对路径/到/pyAutomation/agent-sdk" }
# （SDK 唯一开发地在 pyAutomation/agent-sdk/；.claude/skills/agent-sdk/ 是只读同步镜像，
#  不要把 path 指向镜像——改镜像不会进发布流程）
```

> 发布新版 SDK 到内网源的完整流程（升版→临时目录构建→twine 上传→验证）见主 SKILL.md
> 「SDK 安装与发布（内网 PyPI）」。

对应 README 固定写这几块（哪怕再简单也别省）：

```markdown
## 环境搭建（uv）
cd your-agent-dir
uv sync              # 建 .venv 并装好 pyauto-agent 及其依赖

外网下载超时时走本地代理：
set HTTPS_PROXY=http://127.0.0.1:<代理端口>
set HTTP_PROXY=http://127.0.0.1:<代理端口>
uv sync

## 运行
uv run python your_agent.py
# 默认：平台 = http://192.168.2.13:5000（内网生产），public_url 自动探测本机内网 IP。
# 偏离默认时覆盖：
set PYAUTO_PLATFORM_URL=http://127.0.0.1:5000        # 本地起平台调试
set PYAUTO_AGENT_PUBLIC_URL=http://<本机内网IP>:<端口>  # 多网卡/端口冲突时指定

## 派发测试
curl -X POST http://192.168.2.13:5000/agent_platform/a2a/dispatch \
  -H "Authorization: Bearer <JWT>" -H "Content-Type: application/json" \
  -d '{"agent_name": "your-agent-name", "message": "..."}'
```

**目录归属原则**：官方 SDK 自带的通用示例进 `agent-sdk/examples/`（本目录本身即模板实例，
`cd examples && uv sync` 直接跑，不需要 `--project`）；某个具体项目专用的 agent（会调该项目
的构建/测试/p4 等命令）进项目自己的 `Tools/<AgentName>/` 之类目录，同样用这套
`pyproject.toml` + README 骨架，不要和 `agent-sdk` 混在一起、也不要裸 `pip install`。
在库实例：`Tools/HelloWorldAgent/`——内网源（pl-internal）安装 + 无平台本机 JSON-RPC 冒烟
命令齐全（已实测通过），新建 agent 直接以它为起点复制改名即可。
生产级在库实例：`Tools/agents/WinBuilder3MainAgent/`（winbuilder3-main-agent）——任务全部转发本机
pi coding-agent 在项目根异步执行：双 lane 任务队列（排他串行 + 只读并发）、job_id 异步受理
规避 600s 派发超时、`--append-system-prompt` 注入 RESULT 结论块规范、第二端口只读日志/报告
下载服务。做「转发 pi / 长任务 / 排他队列」类 agent 时参考它。

## 冒烟测试

本地端到端验证一个新 agent：

1. 起平台后端（开发可用 SQLite/临时库；生产库测试记得 `DISABLE_SCHEDULER=1` 避免误触计划任务）。
2. `PYAUTO_PLATFORM_URL=http://127.0.0.1:5000 PYAUTO_AGENT_PUBLIC_URL=http://127.0.0.1:9000 python your_agent.py`
3. 看日志出现 `registered: agent_id=...`；前端「Agent 平台监控」应显示该 agent **online**。
4. 前端对它「派发」一段消息（或 `POST /agent_platform/a2a/dispatch {"agent_name": "...", "message": "..."}`），
   看派发历史变 completed、结果正确。
5. 杀掉 agent 进程 → 最迟 ~3 分钟变 offline；对 offline agent 派发应立即失败。

> 排障（注册失败/心跳掉线/代理 502/版本头）见 [troubleshooting](troubleshooting.md)。
