# coding: utf-8
"""进阶示例：收到平台派发的消息后，转发给本机的 `pi` coding-agent CLI（大模型），
把 pi 的最终回复文本作为结果回传平台。适用于任何本机已装好 `pi` CLI 的场景，
不局限于某个具体项目——把 PI_BIN / 平台地址换掉即可复用。

调用链：
    平台 --dispatch--> 本 agent skill handler --subprocess--> pi CLI --调用大模型--> 回复文本
    平台 <--artifact(text)-----------------------------------------------------------

关于"异步"：pyauto_agent 的 SkillRouterExecutor 已经用 asyncio.to_thread() 在独立线程里跑
handler（见 pyauto_agent/executor.py），所以这里的 subprocess.run() 即使阻塞几十秒也不会卡住
agent 的事件循环/心跳线程；不需要再额外起线程或 asyncio 包装。

调用 pi 的方式选了 `pi -p "<prompt>" --no-session`：
    - `-p/--print`：一次性问答模式，stdout 直接是模型最终回复的纯文本，不需要再解析事件流
    - `--no-session`：不写会话文件，避免每次派发在磁盘堆历史 session
若想要结构化事件（token 用量、工具调用记录等），可以换成 `pi --mode json` 自己过滤
`message_end`/`agent_end` 事件，或用 `pi --mode rpc` 走 stdin/stdout JSONL 双向协议；
具体见 pi CLI 自身文档（`pi --help` / docs/json.md / docs/rpc.md）。

用法:
    1. 确认本机 `pi` CLI 已可用（`where pi` 能找到 pi.cmd/pi）
    2. python examples/pi_relay_agent.py
    3. 平台派发任意文本，会转发给 pi 问答并回传模型的最终回复

Windows 上的坑：npm 全局命令实际落地是 `pi.cmd`，Win32 CreateProcess 在 subprocess
shell=False 时不会像 cmd.exe 一样按 PATHEXT 自动补全后缀，直接传 "pi" 会 FileNotFoundError
（即使 `where pi` 能找到）。用 shutil.which() 显式解析出真实路径，不要改用 shell=True。
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from urllib.parse import urlparse

from pyauto_agent import AgentApp

# 内网生产平台（192.168.2.13 同时是内网 PyPI 宿主）；本地起平台调试用环境变量覆盖
PLATFORM_URL = os.getenv("PYAUTO_PLATFORM_URL", "http://192.168.2.13:5000")


def _local_ip() -> str:
    # public_url 必须平台可达：探测通往平台那块网卡的本机内网 IP（UDP connect 不发包）
    probe = urlparse(PLATFORM_URL).hostname or "192.168.2.13"
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((probe, 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


PUBLIC_URL = os.getenv("PYAUTO_AGENT_PUBLIC_URL", f"http://{_local_ip()}:9997")

PI_TIMEOUT = int(os.getenv("PI_TIMEOUT", "120"))         # 单次问答超时（秒）
MAX_OUTPUT_CHARS = 20000

app = AgentApp(
    name=os.getenv("PYAUTO_AGENT_NAME", "pi-relay-agent"),
    description="收到消息后转发给本机 pi agent（大模型），回传模型的最终回复文本",
    platform_url=PLATFORM_URL,
    public_url=PUBLIC_URL,
    owner=os.getenv("PYAUTO_AGENT_OWNER", ""),
    register_key=os.getenv("PYAUTO_REGISTER_KEY", ""),
)


def _resolve_pi_bin() -> str | None:
    """解析 pi 可执行文件的完整路径（见文件顶部 Windows 坑说明）。"""
    override = os.getenv("PI_BIN")
    if override:
        return override
    return shutil.which("pi")


def _call_pi(prompt: str) -> str:
    """调用 `pi -p <prompt> --no-session`，返回模型最终回复的纯文本。

    prompt 作为独立 argv 元素传给 subprocess（shell=False），不经过 shell 解释，
    不存在命令注入风险；即使 prompt 里含引号/换行/特殊字符也会被原样当作一个参数传递。
    """
    pi_bin = _resolve_pi_bin()
    if not pi_bin:
        return "[error] pi CLI not found on PATH; check 'npm link' setup or set PI_BIN to full path"

    argv = [pi_bin, "-p", prompt, "--no-session"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                               timeout=PI_TIMEOUT, shell=False)
    except FileNotFoundError:
        return f"[error] failed to launch resolved pi binary: {pi_bin}"
    except subprocess.TimeoutExpired:
        return f"[error] pi call timed out after {PI_TIMEOUT}s"
    except Exception as e:
        return f"[error] failed to start pi: {e}"

    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        return f"[error] pi exited with code {proc.returncode}: {err[:2000]}"

    text = (proc.stdout or "").strip()
    if not text:
        err = (proc.stderr or "").strip()
        return f"[error] pi returned empty output. stderr: {err[:2000]}"
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"\n...[truncated, total {len(text)} chars]"
    return text


@app.skill(id="ask_pi", name="Ask Pi Agent",
           description="把收到的文本转发给本机 pi agent（大模型），返回模型的最终回复",
           tags=["llm", "pi", "relay"],
           examples=["用一句话解释什么是 A2A 协议"])
def ask_pi(text: str) -> str:
    prompt = text.strip()
    if not prompt:
        return "[rejected] empty prompt"
    return _call_pi(prompt)


if __name__ == "__main__":
    port = int(PUBLIC_URL.rsplit(":", 1)[-1])
    app.run(host="0.0.0.0", port=port)
