# coding: utf-8
"""最小示例：Echo agent（改编自 a2a-samples helloworld，免任何 LLM key）。

运行:
    python examples/hello_agent.py

然后在平台监控页应能看到 hello-agent 在线，派发任意文本会原样回显。
"""
import os
import socket
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


PUBLIC_URL = os.getenv("PYAUTO_AGENT_PUBLIC_URL", f"http://{_local_ip()}:9999")

app = AgentApp(
    name=os.getenv("PYAUTO_AGENT_NAME", "hello-agent"),
    description="Echo 示例 agent：原样回显收到的文本",
    platform_url=PLATFORM_URL,
    public_url=PUBLIC_URL,
    owner=os.getenv("PYAUTO_AGENT_OWNER", ""),
    register_key=os.getenv("PYAUTO_REGISTER_KEY", ""),
)


@app.skill(id="echo", name="Echo Bot", description="原样回显收到的文本",
           tags=["demo", "echo"], examples=["hi", "hello world"])
def echo(text: str) -> str:
    return f"Hello from {app.name}! I received: {text}"


if __name__ == "__main__":
    port = int(PUBLIC_URL.rsplit(":", 1)[-1])
    app.run(host="0.0.0.0", port=port)
