# coding: utf-8
"""压制 SDK 内部周期性 HTTP 请求（心跳/锁续租/锁轮询）产生的 httpx INFO 日志。

httpx 对每个请求都会经 "httpx" logger 打一条 INFO（`HTTP Request: ...`）。
心跳每 30s 一条、锁 acquire 轮询/续租同样高频，会淹没宿主进程的业务日志。
`app.run()` 里的 `setLevel(WARNING)` 只保护经 run() 启动的 agent——宿主若自行
`basicConfig`/`dictConfig`、或独立使用 RegistrationClient / TeamCityWorkspaceLock，
压制就会失效。

这里改用**定向 Filter**：挂在 "httpx" logger 对象上（import SDK 即生效），只丢弃
命中平台内部端点的 INFO 请求行；宿主自己的 httpx 业务请求日志、以及 WARNING 及
以上（如心跳失败）完全不受影响。Filter 挂在 logger 对象上，后续 basicConfig /
setLevel 都不会把它移除。
"""
import logging

# SDK 周期性调用的平台内部端点：命中即静音（只影响 httpx 的 INFO 请求行）
_QUIET_PATH_MARKERS = (
    "/agent_platform/a2a/agents/",   # register / heartbeat / unregister
    "/teamcity/agent_lock/",         # acquire 轮询 / heartbeat 续租 / release
)


class _InternalRequestFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno > logging.INFO:
            return True
        msg = record.getMessage()
        return not any(marker in msg for marker in _QUIET_PATH_MARKERS)


def silence_internal_http_logs() -> None:
    """幂等：给 httpx logger 挂上内部端点静音 Filter。"""
    lg = logging.getLogger("httpx")
    if not any(isinstance(f, _InternalRequestFilter) for f in lg.filters):
        lg.addFilter(_InternalRequestFilter())
