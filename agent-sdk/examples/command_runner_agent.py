# coding: utf-8
"""本地命令执行 agent：只执行白名单别名对应的固定命令（安全默认）。

用法:
    1. 编辑同目录 command_whitelist.json，维护 别名 -> 固定 argv 列表
    2. python examples/command_runner_agent.py
    3. 平台派发消息 "run_cmd: <别名>"（或直接 "<别名>"）即在本机执行对应命令

安全说明:
    - 只允许白名单里的固定 argv，不拼接、不解释任意 shell 字符串
    - 白名单文件由 agent 所有者本人维护，加什么命令自己负责
    - 每条命令有超时（默认 300s），stdout/stderr 截断后回传
"""
import json
import os
import socket
import subprocess
from urllib.parse import urlparse

from pyauto_agent import AgentApp

_HERE = os.path.dirname(os.path.abspath(__file__))
WHITELIST_FILE = os.getenv("PYAUTO_CMD_WHITELIST",
                           os.path.join(_HERE, "command_whitelist.json"))
COMMAND_TIMEOUT = int(os.getenv("PYAUTO_CMD_TIMEOUT", "300"))
MAX_OUTPUT_CHARS = 20000

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


PUBLIC_URL = os.getenv("PYAUTO_AGENT_PUBLIC_URL", f"http://{_local_ip()}:9998")

app = AgentApp(
    name=os.getenv("PYAUTO_AGENT_NAME", "cmd-runner-agent"),
    description="在本机执行白名单内的固定命令并回传输出",
    platform_url=PLATFORM_URL,
    public_url=PUBLIC_URL,
    owner=os.getenv("PYAUTO_AGENT_OWNER", ""),
    register_key=os.getenv("PYAUTO_REGISTER_KEY", ""),
)


def _load_whitelist() -> dict:
    """每次执行时重读，编辑白名单无需重启 agent。"""
    with open(WHITELIST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    allowed = data.get("allowed_commands") or {}
    return {alias: argv for alias, argv in allowed.items()
            if isinstance(argv, list) and argv}


@app.skill(id="run_cmd", name="Run Whitelisted Command",
           description="执行白名单别名对应的本地命令，回传 stdout/stderr",
           tags=["shell", "local", "command"],
           examples=["list_dir", "run_cmd: system_info"])
def run_cmd(text: str) -> str:
    alias = text.strip()
    try:
        whitelist = _load_whitelist()
    except Exception as e:
        return f"[error] cannot load whitelist {WHITELIST_FILE}: {e}"

    if alias not in whitelist:
        allowed = ", ".join(sorted(whitelist)) or "(empty)"
        return f"[rejected] '{alias}' is not in whitelist. Allowed: {allowed}"

    argv = whitelist[alias]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=COMMAND_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"[error] '{alias}' timed out after {COMMAND_TIMEOUT}s"
    except Exception as e:
        return f"[error] '{alias}' failed to start: {e}"

    out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
    if len(out) > MAX_OUTPUT_CHARS:
        out = out[:MAX_OUTPUT_CHARS] + f"\n...[truncated, total {len(out)} chars]"
    return f"[exit code {proc.returncode}] {alias}\n{out}"


if __name__ == "__main__":
    port = int(PUBLIC_URL.rsplit(":", 1)[-1])
    app.run(host="0.0.0.0", port=port)
