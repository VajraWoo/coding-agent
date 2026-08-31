"""In-memory multi-turn conversation state for one Agent instance."""

from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Any, Callable

from .agent import Agent, AgentEvent, AgentRunResult
from .errors import ConversationBusyError


class Conversation:
    """Serialize user turns and retain only successfully completed history."""

    def __init__(self, agent: Agent) -> None:
        self._agent = agent
        self._history: tuple[dict[str, Any], ...] = ()
        self._run_lock = Lock()
        self._history_lock = Lock()

    @property
    def history(self) -> list[dict[str, Any]]:
        with self._history_lock:
            return deepcopy(list(self._history))

    def send(
        self,
        task: str,
        *,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentRunResult:
        if not self._run_lock.acquire(blocking=False):
            raise ConversationBusyError("当前会话已有任务正在运行，请等待完成。")
        try:
            with self._history_lock:
                prior_history = deepcopy(self._history) or None
            result = self._agent.run(
                task,
                on_event=on_event,
                history=prior_history,
            )
            with self._history_lock:
                self._history = deepcopy(result.history)
            return result
        finally:
            self._run_lock.release()

    def reset(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            raise ConversationBusyError("任务运行时不能重置会话。")
        try:
            with self._history_lock:
                self._history = ()
        finally:
            self._run_lock.release()
