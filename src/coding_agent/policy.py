"""Program-enforced tool permissions and human approval boundaries."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from .tools import ToolResult


Mode = Literal["ask", "develop"]
_READ_TOOLS = frozenset({"list_files", "read_file"})
_SIDE_EFFECT_TOOLS = frozenset({"write_file", "run_command"})


class ToolCollection(Protocol):
    def schemas(self) -> list[dict[str, Any]]: ...

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult: ...


@dataclass(frozen=True)
class ApprovalRequest:
    """The exact side-effect request shown to a human before execution."""

    tool_name: str
    arguments: dict[str, Any]


ApprovalCallback = Callable[[ApprovalRequest], bool]


class PolicyTools:
    """Restrict tool discovery and execution according to one session mode."""

    def __init__(
        self,
        tools: ToolCollection,
        *,
        mode: Mode,
        approve: ApprovalCallback | None = None,
        auto_approve: bool = False,
    ) -> None:
        if mode not in {"ask", "develop"}:
            raise ValueError("mode 必须是 'ask' 或 'develop'")
        if not isinstance(auto_approve, bool):
            raise ValueError("auto_approve 必须是布尔值")

        self._tools = tools
        self.mode = mode
        self._approve = approve
        self._auto_approve = auto_approve

    def schemas(self) -> list[dict[str, Any]]:
        schemas = self._tools.schemas()
        if self.mode == "develop":
            return schemas
        return [
            schema
            for schema in schemas
            if schema.get("function", {}).get("name") in _READ_TOOLS
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if self.mode == "ask" and name not in _READ_TOOLS:
            return ToolResult(
                f"只读提问模式禁止调用有副作用的工具: {name}",
                is_error=True,
            )

        if self.mode == "develop" and name in _SIDE_EFFECT_TOOLS:
            if not self._auto_approve:
                if self._approve is None:
                    return ToolResult(
                        f"工具 {name} 尚未获得用户批准，未执行。",
                        is_error=True,
                    )
                request = ApprovalRequest(name, deepcopy(arguments))
                try:
                    approved = self._approve(request)
                except Exception as exc:
                    return ToolResult(f"工具审批失败: {exc}", is_error=True)
                if not approved:
                    return ToolResult(
                        f"用户拒绝执行工具: {name}",
                        is_error=True,
                    )

        return self._tools.execute(name, arguments)
