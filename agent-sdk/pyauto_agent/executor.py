# coding: utf-8
"""通用 AgentExecutor：把 A2A 请求路由到用户注册的 @app.skill handler。

路由规则：消息以 "<skill_id>:" 开头 → 路由到对应 skill，其余文本作为参数；
否则整条文本交给第一个注册的 skill（默认 skill）。
handler 是同步函数（在线程中执行），返回值 str 作为 artifact 回传。
"""
from __future__ import annotations

import asyncio
import logging

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import TaskState

logger = logging.getLogger(__name__)


class SkillRouterExecutor(AgentExecutor):
    def __init__(self, skills: list[tuple[dict, callable]],
                 lock_factory=None, busy_tracker=None, cancel_hook=None):
        """skills: [(skill_meta_dict, handler)]，顺序即注册顺序，第一个为默认 skill。

        skill_meta 可带 `side: True` 标记「侧线 skill」（如 btw 进度查询）：轻量只读
        查询——不参与 busy 记账（不会把主任务的心跳状态冲掉）、不取 workspace 锁
        （否则主任务持锁期间侧线查询会被卡死）。

        :param lock_factory: 可选，无参函数返回 workspace 锁对象（acquire()/release()/
                             held 协议）。非 None 时 **handler 执行前强制持锁**（side
                             skill 除外），拿不到锁任务置 FAILED；finally 必释放。
                             AgentApp 配置了 tc_agent_name 时自动注入（TeamCity
                             workspace 互斥）。
        :param busy_tracker: 可选，task_started(task_id, skill_id, payload)/
                             task_finished() 协议对象；心跳线程据此上报真实工作状态
                             （busy），平台用它续租锁、判定空占。side skill 不触发。
        :param cancel_hook: 可选，无参函数，cancel() 时调用——杀当前正在执行的底层
                             子进程树（如 host 传入 runtime 适配器的 cancel_current），
                             让 to_thread 里的 handler 尽快退出。可选：不传则取消
                             只标记状态，handler 跑完自然结束（结果丢弃）。
        """
        if not skills:
            raise ValueError("at least one @app.skill handler is required")
        self._handlers = {meta["id"]: handler for meta, handler in skills}
        self._side_skills = {meta["id"] for meta, _ in skills if meta.get("side")}
        self._default_id = skills[0][0]["id"]
        self._lock_factory = lock_factory
        self._busy_tracker = busy_tracker
        self._cancel_hook = cancel_hook

    def _route(self, text: str) -> tuple[str, str]:
        head, sep, rest = text.partition(":")
        if sep and head.strip() in self._handlers:
            return head.strip(), rest.strip()
        return self._default_id, text

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task:
            task = context.current_task
        else:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue=event_queue, task_id=task.id,
                              context_id=task.context_id)
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message("Processing request..."),
        )

        text = get_message_text(context.message) or ""
        skill_id, payload = self._route(text)
        handler = self._handlers[skill_id]
        is_side = skill_id in self._side_skills
        logger.info("[pyauto_agent] skill=%s payload=%.200s", skill_id, payload)

        if self._busy_tracker is not None and not is_side:
            self._busy_tracker.task_started(task.id, skill_id, payload)
        # side skill 不取锁：主任务持锁期间侧线查询（btw 等）必须能进来
        lock = (self._lock_factory() if self._lock_factory is not None and not is_side
                else None)
        try:
            # 强制锁：配置了 tc_agent_name 的 agent 必须先持有构建机 workspace 锁
            # 才能推进 handler（等待期间平台已禁用 TC agent、构建在排空/排队）
            if lock is not None:
                try:
                    await asyncio.to_thread(lock.acquire)
                except Exception as e:
                    logger.error("[pyauto_agent] workspace lock not acquired for skill "
                                 "%s: %s", skill_id, e)
                    await updater.update_status(
                        state=TaskState.TASK_STATE_FAILED,
                        message=new_text_message(
                            f"TeamCity workspace lock not acquired: {e}"),
                    )
                    return

            try:
                result = await asyncio.to_thread(handler, payload)
            except Exception as e:
                logger.exception("[pyauto_agent] skill %s handler error", skill_id)
                await updater.update_status(
                    state=TaskState.TASK_STATE_FAILED,
                    message=new_text_message(f"handler error: {e}"),
                )
                return

            # 后处理（附结果 + 置终态）也要兜底：曾经出现过 handler 正常跑完、
            # add_artifact/update_status 抛异常（a2a-sdk 事件队列竞态）被框架层
            # 静默置 FAILED——平台只看到无任何文本的失败任务，结果文本全丢。
            try:
                await updater.add_artifact(
                    parts=[new_text_part(text=str(result), media_type="text/plain")])
                await updater.update_status(
                    state=TaskState.TASK_STATE_COMPLETED,
                    message=new_text_message("done"),
                )
            except Exception as e:
                logger.exception("[pyauto_agent] skill %s result delivery failed", skill_id)
                try:
                    await updater.update_status(
                        state=TaskState.TASK_STATE_FAILED,
                        message=new_text_message(
                            f"result delivery failed: {e}; handler output (first 500 chars): "
                            f"{str(result)[:500]}"),
                    )
                except Exception:
                    logger.exception("[pyauto_agent] skill %s even failure report failed",
                                     skill_id)
        finally:
            # 无论成败必须走到：释放锁（恢复构建机接单）+ busy 复位。
            # release 内部自带重试与服务端 TTL 兜底，不会抛出打断状态回传
            if lock is not None and lock.held:
                await asyncio.to_thread(lock.release)
            if self._busy_tracker is not None and not is_side:
                self._busy_tracker.task_finished()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """平台取消：杀底层子进程（cancel_hook）+ 上报 CANCELED 终态。

        不能再抛 NotImplementedError——a2a-sdk 的 on_cancel_task 是先调
        executor.cancel 再 producer_task.cancel()，抛异常会让后者永远执行不到，
        取消链路整体失效（任务照样跑、平台还收到 RPC 错误）。
        """
        logger.warning("[pyauto_agent] cancel requested for task %s", context.task_id)
        # 顺序敏感：先标记 CANCELED 再杀进程。反过来会让 handler 抢先 EOF 完成、
        # 消费者见到 COMPLETED 终态关闭队列，CANCELED 事件被丢弃（任务永远卡
        # WORKING——实测踩过）。
        updater = TaskUpdater(event_queue=event_queue, task_id=context.task_id,
                              context_id=context.context_id)
        await updater.update_status(
            state=TaskState.TASK_STATE_CANCELED,
            message=new_text_message("canceled by platform"),
        )
        if self._cancel_hook is not None:
            try:
                await asyncio.to_thread(self._cancel_hook)
            except Exception:
                logger.exception("[pyauto_agent] cancel hook failed")
