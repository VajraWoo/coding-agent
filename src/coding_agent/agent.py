"""The project-owned Agent loop connecting a model to local tools."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any, Callable, Protocol

from .errors import AgentLimitError
from .model import ModelResponse
from .tools import ToolResult


DEFAULT_SYSTEM_PROMPT = """You are a coding agent working inside one local workspace.
Use the provided tools to inspect the project before editing it.
Make only changes required by the user's task and run relevant tests when possible.
Treat tool errors as observations: correct the request or explain the limitation.
When the task is complete, respond with a concise summary and verification results."""


class ModelClient(Protocol):
    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResponse: ...


class ToolExecutor(Protocol):
    def schemas(self) -> list[dict[str, Any]]: ...

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult: ...


@dataclass(frozen=True)
class AgentEvent:
    """One observable step emitted by the execution loop."""

    kind: str
    message: str
    round_number: int
    tool_name: str | None = None
    is_error: bool | None = None
    arguments: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentRunResult:
    """Final answer plus the complete protocol history for inspection."""

    final_text: str
    rounds: int
    history: tuple[dict[str, Any], ...]


class Agent:
    """Own conversation history, execute tool calls, and enforce termination."""

    def __init__(
        self,
        model: ModelClient,
        tools: ToolExecutor,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_rounds: int = 12,
    ) -> None:
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("system_prompt 必须是非空字符串")
        if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or max_rounds <= 0:
            raise ValueError("max_rounds 必须是正整数")

        self._model = model
        self._tools = tools
        self._system_prompt = system_prompt
        self._max_rounds = max_rounds

    def run(
        self,
        task: str,
        *,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentRunResult:
        """Run one user task until final model text or the round limit."""
        if not isinstance(task, str) or not task.strip():
            raise ValueError("任务必须是非空字符串")

        history: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": task.strip()},
        ]
        schemas = self._tools.schemas()

        for round_number in range(1, self._max_rounds + 1):
            self._emit(
                on_event,
                AgentEvent("model_request", "正在询问模型下一步", round_number),
            )
            response = self._model.complete(history, tools=schemas)
            history.append(deepcopy(response.assistant_message))

            if response.tool_calls:
                for call in response.tool_calls:
                    self._emit(
                        on_event,
                        AgentEvent(
                            "tool_call",
                            f"模型请求调用 {call.name}",
                            round_number,
                            tool_name=call.name,
                            arguments=deepcopy(call.arguments),
                        ),
                    )
                    result = self._tools.execute(call.name, call.arguments)
                    history.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(
                                {"content": result.content, "is_error": result.is_error},
                                ensure_ascii=False,
                            ),
                        }
                    )
                    self._emit(
                        on_event,
                        AgentEvent(
                            "tool_result",
                            result.content,
                            round_number,
                            tool_name=call.name,
                            is_error=result.is_error,
                        ),
                    )
                continue

            if response.content:
                self._emit(
                    on_event,
                    AgentEvent("final", response.content, round_number),
                )
                return AgentRunResult(
                    final_text=response.content,
                    rounds=round_number,
                    history=tuple(deepcopy(history)),
                )

        raise AgentLimitError(
            f"Agent 在 {self._max_rounds} 轮内没有返回最终答案，已停止。"
        )

    @staticmethod
    def _emit(
        callback: Callable[[AgentEvent], None] | None,
        event: AgentEvent,
    ) -> None:
        if callback is not None:
            callback(event)
