# coding: utf-8
"""pyauto_agent - pyAutomation Agent Platform 本地 agent SDK。

最小用法::

    from pyauto_agent import AgentApp

    app = AgentApp(name="my-pc-agent",
                   platform_url="http://pyauto-server:5000",
                   public_url="http://10.0.0.5:9000")

    @app.skill(id="echo", name="Echo", tags=["demo"])
    def echo(text: str) -> str:
        return f"echo: {text}"

    app.run(host="0.0.0.0", port=9000)
"""
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from pyauto_agent.app import AgentApp
from pyauto_agent.workspace_lock import (
    LockAcquireTimeout,
    TeamCityWorkspaceLock,
    teamcity_workspace_lock,
)

__all__ = ["AgentApp", "TeamCityWorkspaceLock", "teamcity_workspace_lock",
           "LockAcquireTimeout"]
try:
    # 单一事实来源 = pyproject.toml（包元数据），杜绝硬编码版本号不同步
    __version__ = _pkg_version("pyauto-agent")
except PackageNotFoundError:  # 源码目录直接运行（未安装）的兜底
    __version__ = "0.0.0+dev"
