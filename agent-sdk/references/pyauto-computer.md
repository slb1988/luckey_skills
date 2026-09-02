# pyauto-computer 受管模式

平台新一代 agent 接入方式：agent **没有自己的代码目录**，平台托管的 `pyauto-computer` CLI
把 AgentApp + runtime 适配（pi/claude/codex/kimi 等 coding-agent CLI）+ 注册/心跳 +
进程守护全部包掉。适用判断见 SKILL.md 主体的两条路径。

## 系统结构

- **安装**：`irm http://192.168.2.13/pyauto-computer/install.ps1 | iex`（免端口短链，转发到
  平台 `:5000/agent_platform/a2a/computer/install.ps1`）。wheel 由平台 `/computer/packages`
  自托管——pypi-server :8080 挂了也能装；当前版本以该 packages 清单为准
  （`curl --noproxy 192.168.2.13 http://192.168.2.13:5000/agent_platform/a2a/computer/packages`）。
  uv tool 安装，落地 `~/.local/bin`（需在 PATH）。顺带装 `hcom`（agent 间总线，公共 PyPI）。
- **`pyauto-computer setup`**：机器指纹 upsert 登记到平台（**幂等**——同指纹返回同一 computer
  并轮换 token，丢 token 的自愈路径就是重跑 setup）→ 发 computer #N + computer_token，存
  `~/.pyauto/computer.json`；`shutil.which` + `--version` 快探本机 runtime 清单上报平台；
  平台配了 relay token 则自动 `hcom relay connect` 接跨机总线，没配就是本机总线模式。
- **`pyauto-computer agent create <名>`**（在目标工作目录里跑，或 `--dir` 指定）：
  平台先校验名字全局唯一，通过才落地。**workroot=cwd，只在目录里写一个 `.pyauto/`**
  （agent.json manifest / host.pid / logs/），不生成任何工程文件、不污染仓库——目录自有的
  CLAUDE.md / skills 就是 agent 上下文。端口自动从 **9100–9299** 扫描分配（与手写 agent
  惯用的 9995–9999 段错开），也可 `--port` 显式指定。name → 绝对路径映射只存本机
  `~/.pyauto/agents.json`，**平台只记 name**（换机/换目录要重新 create）。
- **`agent start/stop/restart/list/logs/forget <名>`**：start 以 workroot 为 cwd 拉起脱离终端的
  host 进程（`python -m pyauto_computer host`，Windows DETACHED_PROCESS / POSIX
  start_new_session），等 20s 确认端口监听。stop 杀进程树并立即上报平台置 offline（不等
  心跳 TTL）。forget 只删本机映射，平台侧记录要到监控页删。
- **host 的 skill**：默认 skill `run`——派发文本 → runtime CLI headless 一次性执行
  （cwd=workroot，输出截断 20000 字符，默认超时 1800s）→ 回传文本；`bus: @目标 消息`
  前缀走 hcom 总线出站。pi 适配器移植了 WinBuilder3MainAgent/pi_runner.py 的三个硬仗经验
  （.cmd shim 解包成 [node, js] 直跑、多行 prompt 不被 cmd.exe 截断、超时杀整棵进程树，
  见主 SKILL.md 常见坑）。
- **自启模型**：`service install` 只登记**一条** OS 自启项（Windows schtasks onlogon /
  Linux systemd --user + Linger 检查 / macOS LaunchAgent）拉起 `pyauto-computer supervisor`，
  supervisor 按各 agent 的 `--autostart` 标记拉起并守护——新增 agent 不再动系统自启项。
  Windows 上 schtasks 被拒（令牌未提权/策略限制）时的等效替代：Startup 文件夹放一个指向
  `~/.local/bin/pyauto-computer.exe supervisor` 的快捷方式；要完全无窗口改放 VBS
  （`CreateObject("Wscript.Shell").Run """...pyauto-computer.exe"" supervisor", 0, False`）——
  快捷方式登录时会闪现控制台窗口。Sun 本机（2026-08）实测手动 schtasks 与 PowerShell
  `Register-ScheduledTask` 提权执行同样 Access denied（域策略级限制 Task Scheduler，不用再试），
  VBS 方案无需管理员且已验证完整链路：登录 → supervisor → 按 autostart 拉起受管 agent。

## 跨网段 / 受限网络接入（0.4.1 QNAP NAS 实测）

install 短链与真实脚本内部都**硬编码 192.168.2.13**；平台默认地址不可达的机器
（跨网段、异地）按下面来：

- **装 CLI**：用可达地址拉真实脚本、sed 替换内嵌 IP 再执行（短链转发目标也是 2.13，直接跑会超时）：
  ```bash
  curl -fsSL --max-time 30 http://<可达IP>:5000/agent_platform/a2a/computer/install.sh \
    | sed 's/192\.168\.2\.13/<可达IP>/g' | sh
  ```
- **setup**：`PYAUTO_PLATFORM_URL=http://<可达IP>:5000 pyauto-computer setup`。setup 会把
  platform_url 持久化进 `~/.pyauto/computer.json`。
- **坑：env 覆盖不能只在 setup 时给**。`agent create/start/...` 子命令只读
  `consts.platform_url()`（= `PYAUTO_PLATFORM_URL` 或内置默认），**不读 computer.json 里
  持久化的 platform_url**——setup 成功后直接 `agent create` 仍报「平台不可达」。跨网段机器
  必须把 `export PYAUTO_PLATFORM_URL=...` 写进 shell profile（如 `~/.profile`）长期生效。
- **公共 PyPI 也不可达时**（国内服务器/QNAP 常态，与 troubleshooting 的 Clash 方案并列的
  另一条路）：给 uv 传国内镜像 `UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/`
  再跑 install。注意 install.sh 的 pip 兜底分支在 uv 管理的 Python 上会撞 PEP 668
  `externally-managed-environment` 直接失败——uv 主路径必须一次成功，镜像要在执行脚本前就
  export 好。
- 已知跨网段地址：auto-server 在 10.77.77.0/24 网段是 **10.77.77.4**（QNAP NAS 走此地址
  访问平台，:5000 平台 / :80 nginx 短链同源可用）。

## 状态文件位置

| 路径 | 内容 |
|---|---|
| `~/.pyauto/computer.json` | 机器凭证（computer_id/token/指纹），`PYAUTO_HOME` 可覆盖根目录 |
| `~/.pyauto/agents.json` | 本机 name → {path, runtime, port, autostart} 映射 |
| `~/.pyauto/logs/supervisor.log` | supervisor 日志 |
| `<workroot>/.pyauto/agent.json` | agent manifest（name/runtime/port/platform_url） |
| `<workroot>/.pyauto/logs/host.log` | agent 运行日志（rotating 5MB×3） |

**注意**：`<workroot>/.pyauto/` 是本机运行状态（pid/token 关联），不要入版本库——仓库的
忽略规则里加 `.pyauto/*`（本仓库 .p4ignore 已加）。

## 手测冒烟（A2A v1.0 wire 细节）

role 枚举写 `ROLE_USER`（不是 `user`），part 直接 `{"text": "..."}`（**没有 kind 字段**）：

```bash
curl -X POST http://<本机IP>:<port>/ -H "A2A-Version: 1.0" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"SendMessage","params":{"message":{"role":"ROLE_USER","parts":[{"text":"只回复 ok"}],"messageId":"m1"}}}'
```

返回 `TASK_STATE_COMPLETED` + artifacts 里有文本即全链路通（A2A → host → runtime CLI → 回传）。

## 在库实例

| 机器 | computer | agent | 端口 | workroot | 备注 |
|---|---|---|---|---|---|
| WinBuilder3 | #4 | winbuilder3-maindev（agent_id=32） | 9100 | MainDev 仓库根 | 装机细节见 `.team/win-builder/project_pyauto_computer_maindev_agent.md` |
| QNAP NAS453Dmini | #5 | nas | 9100 | `/share/CACHEDEV1_DATA/homes/slb1988` | 跨网段（经 10.77.77.4 访问平台），`PYAUTO_PLATFORM_URL` 已写入 `~/.profile`；runtime=pi，平台未配 relay 走本机总线 |
| Sun（admin 工作机） | #2 | sunlaibing（agent_id=30，runtime=pi） | 9100 | `C:\Users\admin` | autostart=on |
| Sun（admin 工作机） | #2 | sun_maindev（runtime=pi） | 9101 | `D:\MainDev` | autostart=on；本机开机自启 = Startup 文件夹 `pyauto-supervisor.vbs`（域策略拒 schtasks，见上「自启模型」） |
