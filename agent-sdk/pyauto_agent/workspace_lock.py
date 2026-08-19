# coding: utf-8
"""TeamCity 构建机 workspace 互斥锁客户端。

场景：agent 跑在 TeamCity 构建机上、要操作与 TC 构建共享的 P4 workspace。
开工前必须持锁——平台会先禁用该机的 TC agent（新构建自然排队）、等在跑构建
排空，才判定持锁成功；释放时重新 enable。锁经 pyAutomation 后端统一管理
（/teamcity/agent_lock/*），TC token 不出服务端。

用法（独立脚本；AgentApp 传了 tc_agent_name 时 executor 会自动包锁，无需手动调）::

    from pyauto_agent.workspace_lock import teamcity_workspace_lock

    with teamcity_workspace_lock(agent_name="WinBuilder3", owner="wb3-agent",
                                 reason="rebuild nav data") as lock:
        ...  # 独占操作 workspace

行为契约：
- acquire 轮询平台直到 state=acquired；draining（等构建排空）/ held_by_other
  （他人持锁）都继续等待，超过 acquire_timeout 抛 LockAcquireTimeout。
- **超时/异常时若已进入 draining（TC agent 已被禁用），退出前 best-effort
  release**——绝不留下「没拿到锁却禁了构建机」。
- 续租：AgentApp 内使用时由平台心跳自动续租（busy=true）；独立脚本长任务
  传 auto_renew=True 起后台续租线程，或自行周期调 renew()。
- 平台不可达时锁有三重服务端兜底（租约 TTL / sweeper / TC statusSwitchTime），
  不会永久卡死构建机。
"""
from __future__ import annotations

import logging
import threading
import time

import httpx

from pyauto_agent._quiet import silence_internal_http_logs

logger = logging.getLogger(__name__)

# 平台是内网服务，不能走系统代理（开发机 Clash 等会把内网流量 502 掉）
_NO_PROXY = {"trust_env": False}

# acquire 轮询/续租每 30s 一条 httpx INFO 会刷屏：import 即定向静音（见 _quiet.py）
silence_internal_http_logs()

DEFAULT_PLATFORM_URL = "http://192.168.2.13:5000"


class LockAcquireTimeout(RuntimeError):
    """acquire 超时（构建一直排不空 / 他人持锁不放）。"""


class TeamCityWorkspaceLock:
    """可作 context manager，也可手动 acquire()/release()。线程不安全，一任务一实例。"""

    def __init__(self, agent_name: str, owner: str, reason: str = "",
                 platform_url: str = DEFAULT_PLATFORM_URL,
                 ttl_seconds: int = 1800, acquire_timeout: float | None = 3600,
                 poll_interval: float = 30.0, auto_renew: bool = False):
        if not agent_name or not owner:
            raise ValueError("agent_name and owner are required")
        self.agent_name = agent_name
        self.owner = owner
        self.reason = reason
        self.ttl_seconds = ttl_seconds
        self.acquire_timeout = acquire_timeout
        self.poll_interval = poll_interval
        self.auto_renew = auto_renew
        self._base = platform_url.rstrip("/") + "/teamcity/agent_lock"
        self.state: str | None = None       # 最近一次平台返回的锁状态
        self.expires_at: str | None = None
        self._renew_stop = threading.Event()
        self._renew_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    @property
    def held(self) -> bool:
        return self.state == "acquired"

    def _post(self, action: str, payload: dict) -> dict:
        resp = httpx.post(f"{self._base}/{action}", json=payload, timeout=15, **_NO_PROXY)
        data = resp.json()
        status = data.get("status") or {}
        if status.get("code") not in (0,):
            raise RuntimeError(f"{action} failed: code={status.get('code')} "
                               f"result={data.get('result')}")
        return data.get("result") or {}

    # ------------------------------------------------------------------
    def acquire(self) -> "TeamCityWorkspaceLock":
        """轮询获取锁，直到 acquired 或超时。超时/异常自动回滚已产生的 draining。"""
        deadline = (time.monotonic() + self.acquire_timeout
                    if self.acquire_timeout else None)
        entered_draining = False
        try:
            while True:
                result = self._post("acquire", {
                    "agent_name": self.agent_name,
                    "owner": self.owner,
                    "reason": self.reason,
                    "ttl_seconds": self.ttl_seconds,
                })
                self.state = result.get("state")
                self.expires_at = result.get("expires_at")
                if self.state == "acquired":
                    logger.info("[workspace_lock] %s acquired by %s",
                                self.agent_name, self.owner)
                    if self.auto_renew:
                        self._start_renew_thread()
                    return self
                if self.state == "draining":
                    entered_draining = True
                # draining / held_by_other → 继续等（细节走 DEBUG，不刷日志）
                logger.debug("[workspace_lock] %s state=%s, waiting %.0fs",
                             self.agent_name, self.state, self.poll_interval)
                if deadline is not None and time.monotonic() >= deadline:
                    raise LockAcquireTimeout(
                        f"could not acquire lock on {self.agent_name} within "
                        f"{self.acquire_timeout}s (last state: {self.state})")
                time.sleep(self.poll_interval)
        except BaseException:
            # 没拿到锁却可能已把构建机禁了（draining）→ 必须尽力恢复
            if entered_draining and not self.held:
                self._best_effort_release("acquire aborted")
            raise

    def renew(self) -> None:
        """手动续租（AgentApp 内由平台心跳自动续租，无需调用）。"""
        result = self._post("heartbeat", {
            "agent_name": self.agent_name,
            "owner": self.owner,
            "ttl_seconds": self.ttl_seconds,
        })
        self.expires_at = result.get("expires_at")

    def release(self) -> None:
        """释放锁（幂等）。失败重试 3 次后交给服务端 TTL/sweeper 兜底。"""
        self._stop_renew_thread()
        last_err = None
        for attempt in range(3):
            try:
                result = self._post("release", {
                    "agent_name": self.agent_name,
                    "owner": self.owner,
                })
                self.state = result.get("state", "released")
                logger.info("[workspace_lock] %s released by %s",
                            self.agent_name, self.owner)
                return
            except Exception as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
        logger.error("[workspace_lock] release %s failed after retries (%s); "
                     "server-side TTL/sweeper will reclaim", self.agent_name, last_err)

    def _best_effort_release(self, why: str) -> None:
        try:
            self.release()
        except Exception as e:
            logger.error("[workspace_lock] best-effort release failed (%s): %s", why, e)

    # ------------------------------------------------------------------
    def _start_renew_thread(self) -> None:
        self._renew_stop.clear()

        def _loop():
            interval = max(self.ttl_seconds / 3.0, 10.0)
            while not self._renew_stop.wait(interval):
                try:
                    self.renew()
                except Exception as e:
                    logger.warning("[workspace_lock] renew failed: %s", e)

        self._renew_thread = threading.Thread(target=_loop, daemon=True,
                                              name="workspace-lock-renew")
        self._renew_thread.start()

    def _stop_renew_thread(self) -> None:
        self._renew_stop.set()

    # ------------------------------------------------------------------
    def __enter__(self) -> "TeamCityWorkspaceLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def teamcity_workspace_lock(agent_name: str, owner: str, reason: str = "",
                            platform_url: str = DEFAULT_PLATFORM_URL,
                            ttl_seconds: int = 1800,
                            acquire_timeout: float | None = 3600,
                            poll_interval: float = 30.0,
                            auto_renew: bool = False) -> TeamCityWorkspaceLock:
    """便捷入口：`with teamcity_workspace_lock(...) as lock: ...`"""
    return TeamCityWorkspaceLock(agent_name=agent_name, owner=owner, reason=reason,
                                 platform_url=platform_url, ttl_seconds=ttl_seconds,
                                 acquire_timeout=acquire_timeout,
                                 poll_interval=poll_interval, auto_renew=auto_renew)
