# coding: utf-8
"""构建机 workspace 互斥示例：跑在 TeamCity 构建机上的 agent。

关键点只有一个：AgentApp 传 tc_agent_name=本机的 TC agent 名。之后每个任务
执行前 SDK 会自动经平台获取该构建机的 workspace 锁（平台禁用 TC agent →
等在跑构建排空 → 才执行 handler），执行完自动释放；心跳自动上报 busy 状态，
平台据此续租，空占/进程崩溃都会被服务端自动回收。handler 里不需要任何锁代码。

独立脚本（不起 AgentApp）要独占 workspace 时，用底层 helper::

    from pyauto_agent import teamcity_workspace_lock

    with teamcity_workspace_lock(agent_name="WinBuilder3", owner="my-script",
                                 reason="manual p4 sync", auto_renew=True):
        ...  # 长任务传 auto_renew=True 自动续租

运行：uv run python workspace_lock_example.py
"""
import socket
import subprocess

from pyauto_agent import AgentApp

PLATFORM_URL = "http://192.168.2.13:5000"


def _local_ip() -> str:
    """UDP connect 到平台宿主取路由源地址（不实际发包，多网卡也选对网卡）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.2.13", 80))
        return s.getsockname()[0]
    finally:
        s.close()


app = AgentApp(
    name="winbuilder3-workspace-agent",
    description="WinBuilder3 上的 workspace 操作 agent（与 TC 构建互斥）",
    platform_url=PLATFORM_URL,
    public_url=f"http://{_local_ip()}:9100",
    owner="devops",
    tc_agent_name="WinBuilder3",     # ← 声明本机构建机名，启用强制锁
    lock_acquire_timeout=3600,       # 最多等构建排空 1 小时
)


@app.skill(id="p4_clean", name="P4 Clean Workspace", tags=["p4", "workspace"])
def p4_clean(text: str) -> str:
    """执行到这里时已持有 WinBuilder3 的 workspace 锁（TC agent 已禁用、构建已排空）。"""
    result = subprocess.run(["p4", "clean", "-n"], capture_output=True, text=True,
                            timeout=1800)
    return result.stdout[-4000:] or result.stderr[-4000:] or "done"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9100)
