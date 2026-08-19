# coding: utf-8
"""AgentApp：AgentCard 构建 + Starlette 服务 + 平台注册心跳，一行 run() 拉起。"""
from __future__ import annotations

import hmac
import logging
import os
import threading
import time

import uvicorn
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from pyauto_agent.executor import SkillRouterExecutor
from pyauto_agent.registration import RegistrationClient

logger = logging.getLogger(__name__)


class _BusyState:
    """线程安全的真实工作状态：executor 在任务进/出时置位，心跳线程 snapshot()
    上报给平台（平台据此为 TC workspace 锁续租、判定空占）。"""

    def __init__(self):
        self._mu = threading.Lock()
        self._busy = False
        self._task_id: str | None = None
        self._skill_id: str | None = None
        self._payload: str = ""
        self._started_at: float | None = None

    def task_started(self, task_id: str, skill_id: str, payload: str = "") -> None:
        with self._mu:
            self._busy = True
            self._task_id = task_id
            self._skill_id = skill_id
            self._payload = (payload or "")[:1000]
            self._started_at = time.time()

    def task_finished(self) -> None:
        with self._mu:
            self._busy = False
            self._task_id = None
            self._skill_id = None
            self._payload = ""
            self._started_at = None

    def current_run_info(self) -> dict:
        """侧线查询用的完整状态（含 payload/已跑时长；心跳 snapshot 的超集）。"""
        with self._mu:
            return {
                "busy": self._busy,
                "task_id": self._task_id,
                "skill_id": self._skill_id,
                "payload": self._payload,
                "elapsed": (round(time.time() - self._started_at, 1)
                            if self._started_at else None),
            }

    def snapshot(self) -> dict:
        with self._mu:
            return {
                "busy": self._busy,
                "current_task_id": self._task_id,
                "current_skill_id": self._skill_id,
            }


class _ActiveLocks:
    """进程内在持/在等的 workspace 锁登记表：退出/被踢时 best-effort 释放，
    不留下被禁用的构建机（服务端另有 TTL/sweeper/statusSwitchTime 三重兜底）。"""

    def __init__(self):
        self._mu = threading.Lock()
        self._locks = set()

    def track(self, lock) -> None:
        with self._mu:
            self._locks.add(lock)

    def untrack(self, lock) -> None:
        with self._mu:
            self._locks.discard(lock)

    def release_all(self) -> None:
        with self._mu:
            locks = list(self._locks)
            self._locks.clear()
        for lock in locks:
            try:
                lock.release()
            except Exception:
                logger.exception("[pyauto_agent] release lock on shutdown failed")


def _exit_on_platform_deleted() -> None:
    """默认被踢回调：立刻退出进程（SDK ≥0.3.0）。

    典型场景是 hello_agent 之类的测试 demo 有人跑完忘关：管理员在平台点删除，
    这个挂着的进程就地退出、释放名字，任何人重启 agent 重新注册即可回归。
    用 os._exit 而非 sys.exit——本回调在心跳守护线程里触发，sys.exit 只会
    结束该线程，杀不掉主线程里阻塞的 uvicorn。
    """
    logger.warning("[pyauto_agent] kicked by platform (agent deleted); exiting process. "
                   "Restart this agent to re-register.")
    os._exit(0)


class AgentApp:
    """
    本地 agent 应用。

    :param name:         agent 名称（平台全局唯一，@名 派发用）
    :param platform_url: pyAutomation 平台地址，如 http://pyauto-server:5000
    :param public_url:   本 agent 对内网可达的地址，如 http://10.0.0.5:9000
                         （平台注册时会回抓 <public_url>/.well-known/agent-card.json）
    :param register_key: 平台配置了 AGENT_PLATFORM_REGISTER_KEY 时必填
    :param on_platform_deleted: 平台删除/踢出本 agent 时的回调（触发途径：心跳或注册
                         收 410，或平台主动 POST /_pyauto/shutdown 指令，0.4.0 起），
                         无参函数。**默认直接退出进程**（0.3.0 起）——被踢即释放，
                         重启 agent 重新注册即可回归；若希望被踢后进程继续跑
                         （只脱离平台、HTTP 服务保留），传自定义回调如 lambda: None
    :param tc_agent_name: 本 agent 所在 TeamCity 构建机名（如 "WinBuilder3"，0.5.0 起）。
                         非空时启用 workspace 互斥：**每个任务执行前强制经平台获取该
                         构建机的锁**（平台禁用 TC agent → 等在跑构建排空），执行完
                         自动释放；心跳同时上报 busy 状态供平台续租/空占回收。
                         不在构建机上跑的 agent 不要传。
    :param lock_acquire_timeout: 等锁上限秒数（默认 3600；构建一直排不空/他人持锁
                         超过该时长任务置 FAILED）。lock_ttl_seconds/lock_poll_interval
                         同理透传给 workspace 锁。
    :param on_cancel: 平台取消派发时的回调（无参函数，0.8.0 起）——典型用法是杀
                         当前正在执行的底层子进程树（如 pyauto-computer host 传
                         runtime 适配器的 cancel_current）。不传则取消只标记
                         CANCELED 状态，handler 跑完自然结束（结果被丢弃）。
    """

    def __init__(self, name: str, platform_url: str, public_url: str,
                 description: str = "", owner: str = "", version: str = "0.1.0",
                 register_key: str = "", heartbeat_interval: float = 30.0,
                 on_platform_deleted=None, tc_agent_name: str = "",
                 lock_ttl_seconds: int = 1800, lock_acquire_timeout: float = 3600,
                 lock_poll_interval: float = 30.0, on_cancel=None):
        self.name = name
        self.platform_url = platform_url
        self.public_url = public_url.rstrip("/")
        self.description = description
        self.owner = owner
        self.version = version
        self.register_key = register_key
        self.heartbeat_interval = heartbeat_interval
        self.on_platform_deleted = (on_platform_deleted if on_platform_deleted is not None
                                    else _exit_on_platform_deleted)
        self.tc_agent_name = (tc_agent_name or "").strip()
        self.lock_ttl_seconds = lock_ttl_seconds
        self.lock_acquire_timeout = lock_acquire_timeout
        self.lock_poll_interval = lock_poll_interval
        self._busy_state = _BusyState()
        self._active_locks = _ActiveLocks()
        self._skills: list[tuple[dict, callable]] = []
        # on_cancel: 可选无参函数，平台取消派发时调用（杀底层子进程等，0.8.0 起）；
        # None = 取消只标记 CANCELED 状态，handler 跑完自然结束（结果丢弃）
        self.on_cancel = on_cancel

    @property
    def busy_state(self) -> _BusyState:
        """当前任务状态（侧线 skill 如 btw 读它回答“正在跑什么/跑了多久”）。"""
        return self._busy_state

    # ------------------------------------------------------------------
    def skill(self, id: str, name: str, description: str = "",
              tags: list[str] | None = None, examples: list[str] | None = None,
              side: bool = False):
        """注册一个 skill handler：同步函数 (text: str) -> str。

        side=True 标记侧线 skill（如 btw 进度查询）：轻量只读查询，不参与 busy
        记账（心跳仍报主任务状态）、配置了 tc_agent_name 时也不取 workspace 锁——
        主任务持锁/执行期间侧线查询必须能插进来。
        """
        meta = {
            "id": id,
            "name": name,
            "description": description,
            "tags": list(tags or []),
            "examples": list(examples or []),
            "side": bool(side),
        }

        def decorator(fn):
            self._skills.append((meta, fn))
            return fn

        return decorator

    # ------------------------------------------------------------------
    def build_card(self) -> AgentCard:
        skills = [
            AgentSkill(
                id=meta["id"],
                name=meta["name"],
                description=meta["description"] or meta["name"],
                input_modes=["text/plain"],
                output_modes=["text/plain"],
                tags=meta["tags"],
                examples=meta["examples"],
            )
            for meta, _fn in self._skills
        ]
        return AgentCard(
            name=self.name,
            description=self.description or self.name,
            version=self.version,
            default_input_modes=["text/plain"],
            default_output_modes=["text/plain"],
            capabilities=AgentCapabilities(streaming=False),
            supported_interfaces=[
                AgentInterface(
                    protocol_binding="JSONRPC",
                    url=self.public_url,
                    protocol_version="1.0",
                )
            ],
            skills=skills,
        )

    # ------------------------------------------------------------------
    def _make_shutdown_endpoint(self, reg: RegistrationClient):
        """平台主动踢下线的控制端点（SDK ≥0.4.0）：POST /_pyauto/shutdown。

        鉴权：请求头 X-Agent-Token 必须等于注册时平台签发的 agent_token
        （只有平台 DB 和本进程持有）。校验通过 → 停止心跳/重注册，先回 200
        让平台拿到确认，再延迟触发 on_platform_deleted（默认退出进程）。
        """
        async def shutdown(request):
            supplied = request.headers.get("x-agent-token", "")
            token = reg.token
            if not token or not hmac.compare_digest(supplied, token):
                return JSONResponse({"ok": False, "error": "invalid agent token"},
                                    status_code=403)
            logger.warning("[pyauto_agent] shutdown requested by platform (token verified)")
            reg.halt()

            def _fire():
                # 退出前先归还在持的 workspace 锁，不留下被禁用的构建机
                self._active_locks.release_all()
                try:
                    self.on_platform_deleted()
                except Exception:
                    logger.exception("[pyauto_agent] on_platform_deleted callback failed")

            # 延迟触发：让本响应先落地，默认回调 os._exit(0) 才不会掐断平台看到的应答
            threading.Timer(0.2, _fire).start()
            return JSONResponse({"ok": True})

        return shutdown

    def _make_lock_factory(self):
        """tc_agent_name 非空 → 返回锁工厂（executor 每任务调用一次）；否则 None。"""
        if not self.tc_agent_name:
            return None
        from pyauto_agent.workspace_lock import TeamCityWorkspaceLock

        def factory():
            lock = TeamCityWorkspaceLock(
                agent_name=self.tc_agent_name,
                owner=self.name,
                reason=f"a2a task on agent {self.name}",
                platform_url=self.platform_url,
                ttl_seconds=self.lock_ttl_seconds,
                acquire_timeout=self.lock_acquire_timeout,
                poll_interval=self.lock_poll_interval,
            )
            # 登记到进程级清理表；释放即注销（shutdown 时 release_all 兜底）
            self._active_locks.track(lock)
            orig_release = lock.release

            def _release_and_untrack():
                try:
                    orig_release()
                finally:
                    self._active_locks.untrack(lock)

            lock.release = _release_and_untrack
            return lock

        return factory

    def _build_asgi(self, reg: RegistrationClient) -> Starlette:
        """组装 Starlette 应用：agent card + A2A JSON-RPC + 平台控制端点。"""
        card = self.build_card()
        handler = DefaultRequestHandler(
            agent_executor=SkillRouterExecutor(
                self._skills,
                lock_factory=self._make_lock_factory(),
                busy_tracker=self._busy_state,
                cancel_hook=self.on_cancel,
            ),
            task_store=InMemoryTaskStore(),
            agent_card=card,
        )
        routes = []
        routes.extend(create_agent_card_routes(card))
        routes.extend(create_jsonrpc_routes(handler, "/"))
        routes.append(Route("/_pyauto/shutdown", self._make_shutdown_endpoint(reg),
                            methods=["POST"]))
        return Starlette(routes=routes)

    def run(self, host: str = "0.0.0.0", port: int = 9000, log_level: str = "info") -> None:
        """启动 A2A 服务（阻塞），同时后台注册到平台并维持心跳。"""
        if not self._skills:
            raise RuntimeError("no skill registered; use @app.skill(...) first")

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s")
        # 心跳/锁轮询等内部 HTTP 请求不刷日志：httpx 每个请求都会打一条 INFO
        # （30s 心跳一条会淹没业务日志），统一压到 WARNING。
        # 兜底：即使宿主自配 logging 把级别升回 INFO，_quiet.py 的定向 Filter
        # （registration/workspace_lock import 时安装）仍会静音内部端点的请求行。
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)

        reg = RegistrationClient(
            platform_url=self.platform_url,
            name=self.name,
            public_url=self.public_url,
            owner=self.owner,
            description=self.description,
            register_key=self.register_key,
            heartbeat_interval=self.heartbeat_interval,
            on_deleted=self.on_platform_deleted,
            tc_agent_name=self.tc_agent_name,
            busy_state=self._busy_state,
        )
        asgi_app = self._build_asgi(reg)
        reg.start()
        logger.info("[pyauto_agent] agent '%s' serving on %s:%s (public_url=%s%s)",
                    self.name, host, port, self.public_url,
                    f", tc_agent={self.tc_agent_name}" if self.tc_agent_name else "")
        try:
            uvicorn.run(asgi_app, host=host, port=port, log_level=log_level)
        finally:
            self._active_locks.release_all()
            reg.stop()
