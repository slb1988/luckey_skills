# coding: utf-8
"""平台注册 + 心跳守护线程。

- 启动后先等 uvicorn 起监听（平台注册时会回抓 agent card），注册失败按指数退避重试
- 注册成功后每 heartbeat_interval 秒心跳一次（默认 30s，平台 TTL 默认 120s）
- 心跳收到 401（token 失效，如平台侧重注册轮换）→ 自动重新注册
- 心跳/注册收到 410（平台已删除/踢出本 agent）→ 停止心跳与重注册，不再自动重连；
  重启本进程即可重新注册回归（平台侧是软删，重注册直接复活，无需管理员操作）
- 进程退出时尽力调用 unregister 让平台立即感知下线
"""
from __future__ import annotations

import logging
import os
import threading

import httpx

from pyauto_agent._quiet import silence_internal_http_logs

logger = logging.getLogger(__name__)

# 平台是内网服务，不能走系统代理（开发机 Clash 等会把内网/回环流量 502 掉）
_NO_PROXY = {"trust_env": False}


def _computer_headers() -> dict:
    """pyauto-computer 受管机凭证头（0.6.0 起）：环境变量 PYAUTO_COMPUTER_TOKEN
    由 pyauto-computer CLI 拉起 agent 进程时注入，平台据此把 agent 关联到
    所属 computer（fleet 模型）；未设置时不带头（裸 SDK 行为不变）。"""
    token = (os.getenv("PYAUTO_COMPUTER_TOKEN") or "").strip()
    return {"X-Computer-Token": token} if token else {}

# 心跳每 30s 一条 httpx INFO 请求日志会淹没业务日志：import 即定向静音（见 _quiet.py）
silence_internal_http_logs()


class RegistrationClient:
    def __init__(self, platform_url: str, name: str, public_url: str,
                 owner: str = "", description: str = "", register_key: str = "",
                 heartbeat_interval: float = 30.0, on_deleted=None,
                 tc_agent_name: str = "", busy_state=None):
        self._base = platform_url.rstrip("/") + "/agent_platform/a2a"
        self._name = name
        self._public_url = public_url
        self._owner = owner
        self._description = description
        self._register_key = register_key
        self._interval = heartbeat_interval
        self._on_deleted = on_deleted
        # TC 构建机绑定（workspace 互斥锁）：注册时始终上报（"" = 清除服务端绑定）
        self._tc_agent_name = tc_agent_name or ""
        # busy_state: snapshot() -> dict 协议对象（app._BusyState），心跳 body 数据源；
        # None = 不带 body（行为等同旧版 SDK）
        self._busy_state = busy_state
        self.deleted = False
        self._token: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def token(self) -> str | None:
        """当前平台签发的 agent_token（注册成功前为 None）。shutdown 端点鉴权用。"""
        return self._token

    def halt(self) -> None:
        """外部指令（如平台 shutdown）要求脱离平台：置 deleted、停心跳/重注册线程。"""
        self.deleted = True
        self._stop.set()

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="pyauto-agent-heartbeat")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._token:
            try:
                httpx.post(f"{self._base}/agents/unregister",
                           headers={"X-Agent-Token": self._token}, timeout=5, **_NO_PROXY)
                logger.info("[pyauto_agent] unregistered from platform")
            except Exception as e:
                logger.warning("[pyauto_agent] unregister failed: %s", e)

    # ------------------------------------------------------------------
    def _mark_deleted(self, where: str) -> None:
        """平台明确告知本 agent 已被删除/踢出（HTTP 410）：停止心跳与重注册。

        与 401（token 失效，应重注册）语义相反——410 表示平台管理员主动移除，
        自动重连会导致"删了又复活"。回归方式：重启本进程即可（重注册直接复活）。
        """
        logger.warning(
            "[pyauto_agent] platform reports agent deleted (%s); "
            "stopping heartbeat/re-register. To rejoin: just restart this agent "
            "process (it will re-register).", where)
        self.deleted = True
        self._token = None
        self._stop.set()
        if self._on_deleted is not None:
            try:
                self._on_deleted()
            except Exception:
                logger.exception("[pyauto_agent] on_platform_deleted callback failed")

    def _register(self) -> bool:
        try:
            resp = httpx.post(f"{self._base}/agents/register", json={
                "name": self._name,
                "url": self._public_url,
                "owner": self._owner,
                "description": self._description,
                "register_key": self._register_key,
                "tc_agent_name": self._tc_agent_name,
                # 工作目录（0.7.0 起）：注册即上报进程 cwd（pyauto-computer 受管 agent
                # 即 workroot），平台监控页据此展示；重注册自动刷新
                "workdir": os.getcwd(),
            }, headers=_computer_headers(), timeout=15, **_NO_PROXY)
            data = resp.json()
        except Exception as e:
            logger.warning("[pyauto_agent] register failed (platform unreachable): %s", e)
            return False
        if resp.status_code == 410:
            self._mark_deleted("register")
            return False
        status = data.get("status") or {}
        if resp.status_code == 200 and status.get("code") == 0:
            self._token = data["result"]["agent_token"]
            logger.info("[pyauto_agent] registered: agent_id=%s",
                        data["result"].get("agent_id"))
            return True
        logger.warning("[pyauto_agent] register rejected: http=%s resp=%s",
                       resp.status_code, data)
        return False

    def _heartbeat(self) -> None:
        # 心跳静音契约：成功不产生任何日志（每 30s 一条会淹没业务日志），
        # 只在失败/token 失效/被踢时打 warning。httpx 自身的 INFO 请求日志
        # 由 _quiet.py 的定向 Filter 静音（import 即生效，宿主自配 logging 也有效），
        # app.run() 另将 httpx/httpcore 整体压到 WARNING 作为默认安静档。
        try:
            body = self._busy_state.snapshot() if self._busy_state is not None else None
            resp = httpx.post(f"{self._base}/agents/heartbeat",
                              headers={"X-Agent-Token": self._token or "",
                                       **_computer_headers()},
                              json=body, timeout=10,
                              **_NO_PROXY)
        except Exception as e:
            logger.warning("[pyauto_agent] heartbeat failed (platform unreachable): %s", e)
            return
        if resp.status_code == 410:
            self._mark_deleted("heartbeat")
            return
        if resp.status_code == 401:
            logger.warning("[pyauto_agent] heartbeat token rejected, will re-register")
            self._token = None

    def _loop(self) -> None:
        # 给 uvicorn 一点启动时间，注册时平台会回抓本 agent 的 card
        self._stop.wait(2)
        backoff = 5.0
        while not self._stop.is_set():
            if self._token is None:
                if self._register():
                    backoff = 5.0
                else:
                    self._stop.wait(backoff)
                    backoff = min(backoff * 2, 120.0)
                    continue
            self._stop.wait(self._interval)
            if self._stop.is_set():
                return
            self._heartbeat()
