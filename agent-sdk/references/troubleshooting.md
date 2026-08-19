# 代理 Agent 常见坑与排障

> 从主 SKILL.md 移出（长度控制）。注册/心跳/代理/协议版本/Windows 进程坑都在这里。

- **注册一直重试失败**：平台回抓不到 card。查 `public_url` 是否平台可达、防火墙是否放行端口。
- **register rejected: invalid register_key**：平台配了 `AGENT_PLATFORM_REGISTER_KEY`，`AgentApp(register_key=...)` 要一致。
- **名称冲突 already registered with a different url**：换 name，或在原机器用同一 url 重注册。
- **平台/agent 互调走了系统代理被 502**：开发机 Clash 等代理会劫持内网/回环流量。SDK 内所有 httpx
  已 `trust_env=False`；自己写 httpx 调用也要加，否则注册/心跳/派发全 502。
- **装不上/升级失败（公共 PyPI 不通）**：内网机器常态。有 Clash 先 `set HTTPS_PROXY=http://127.0.0.1:7897`
  再试；无代理的国内机器改用镜像：`UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/`
  （腾讯云/清华源亦可）再跑 install 脚本——注意脚本的 pip 兜底分支在 uv 管理的 Python 上会撞
  PEP 668 `externally-managed-environment` 直接失败，uv 主路径必须一次成功。两条路都不行用
  离线 playbook——从平台托管 wheel 页 curl 两个 wheel 到本地，
  `uv tool install --force --offline --with <本地 agent wheel> <本地 computer wheel>`
  （公共依赖走 uv 缓存，装过的机器缓存齐全；首次全新机器则必须先解决 PyPI 可达性）。
- **install.ps1 假成功**：已修复（v2026-08 起显式查 `$LASTEXITCODE`）——原生命令非零退出不触发
  PowerShell catch，旧版脚本 uv 失败仍打印"安装完成"。自己写 PowerShell 调外部命令同理。
- **协议版本**：本 SDK 用 a2a-sdk 1.1.0（A2A v1.0）；平台请求带 `A2A-Version: 1.0` 头，方法名 PascalCase
  `SendMessage`/`GetTask`/`CancelTask`。手写 agent 时对齐，否则被 v1.0 handler 按 0.3 拒绝。
- **Windows 上 handler 里 `subprocess.run(["某命令", ...], shell=False)` 报 `FileNotFoundError`，
  但 `where 某命令` 能找到**：该命令的 Windows 实体是 `.cmd`/`.bat`。Win32 `CreateProcess`
  在 `shell=False` 时不按 `PATHEXT` 补全后缀。修法是用 `shutil.which("某命令")` 解析真实路径再传，
  不要改用 `shell=True`（破坏「不解释任意输入」的安全模型）。
- **上一条的深化：即使 which 解析出了 `.cmd`，参数含换行仍会被整条截断**。`CreateProcess` 运行批处理
  时隐式经 `cmd.exe /c` 重解析命令行，在首个换行处截断——多行 prompt 只剩第一行（且退出码仍是 0，
  极难察觉）。修法：读 `.cmd` shim 内容解析出真实 JS 入口，改为 `[node, js_path, ...]` 直接执行。
  在库实现：`Tools/agents/WinBuilder3MainAgent/pi_runner.py` 的 `resolve_pi_invocation()`。
- **pi 用户级技能/扩展目录是 `~/.pi/agent/skills|extensions`，不是 `~/.pi/skills|extensions`**（根目录
  可用 `PI_CODING_AGENT_DIR` 覆盖）。项目级 `.pi/skills|extensions` 受 trust 门控：headless `-p` 模式
  未 trust 时项目扩展**静默不加载**——无人值守派发要固定加 `-a/--approve`。在库实现：
  `pi_runner.py` 的 `build_argv()` 与 `pi_capability_report()`。
- **Linux 上杀 pi 进程树**：pi → node → 子命令是多级进程链，`proc.kill()` 只杀最外层。修法：
  `Popen(..., start_new_session=True)` + `os.killpg(os.getpgid(pid), SIGKILL)` 全组杀。
  见 `pi_runner.py` 的 `_kill_tree()`（Windows/POSIX 双分支）。
