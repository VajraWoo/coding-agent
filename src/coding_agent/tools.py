"""Workspace-scoped tools exposed to the language model."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .errors import ToolError, ToolValidationError

_TRUNCATION_MARKER = "\n...[输出已截断]"
_IGNORED_DIRECTORIES = {".git", ".venv", "__pycache__", ".pytest_cache"}
_SENSITIVE_ENV_MARKERS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "AUTH",
    "COOKIE",
)


@dataclass(frozen=True)
class ToolResult:
    """A normalized observation that can later be sent back to the model."""

    content: str
    is_error: bool = False


class WorkspaceTools:
    """Validate and execute a fixed set of tools inside one workspace."""

    def __init__(
        self,
        workspace: Path | str,
        *,
        command_timeout_seconds: float = 30.0,
        max_output_chars: int = 20_000,
        max_list_entries: int = 200,
        max_write_chars: int = 100_000,
    ) -> None:
        root = Path(workspace).resolve()
        if not root.is_dir():
            raise ValueError(f"工作目录不存在或不是目录: {root}")
        if command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds 必须大于 0")
        if max_output_chars <= 0 or max_list_entries <= 0 or max_write_chars <= 0:
            raise ValueError("工具输出和写入上限必须大于 0")

        self.workspace = root
        self.command_timeout_seconds = command_timeout_seconds
        self.max_output_chars = max_output_chars
        self.max_list_entries = max_list_entries
        self.max_write_chars = max_write_chars

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Dispatch an untrusted model request through the approved registry."""

        handlers: dict[str, Callable[[dict[str, Any]], ToolResult]] = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "write_file": self._write_file,
            "run_command": self._run_command,
        }
        handler = handlers.get(name)
        if handler is None:
            return ToolResult(f"未知工具: {name}", is_error=True)
        if not isinstance(arguments, dict):
            return ToolResult("工具参数必须是 JSON 对象", is_error=True)

        try:
            return handler(arguments)
        except (ToolError, OSError, UnicodeError) as exc:
            return ToolResult(str(exc), is_error=True)

    def schemas(self) -> list[dict[str, Any]]:
        """Return OpenAI-compatible function schemas for the approved tools."""

        return [
            _function_schema(
                "list_files",
                "List files and directories inside the workspace.",
                {
                    "path": {"type": "string", "description": "Relative directory, default '.'"},
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 8},
                },
                [],
            ),
            _function_schema(
                "read_file",
                "Read a UTF-8 text file inside the workspace.",
                {"path": {"type": "string", "description": "Relative file path"}},
                ["path"],
            ),
            _function_schema(
                "write_file",
                "Create or overwrite a UTF-8 text file inside the workspace.",
                {
                    "path": {"type": "string", "description": "Relative file path"},
                    "content": {"type": "string", "description": "Complete file content"},
                },
                ["path", "content"],
            ),
            _function_schema(
                "run_command",
                "Run one program in the workspace without invoking a shell.",
                {
                    "argv": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "Argument vector, for example ['python', '-m', 'pytest']",
                    }
                },
                ["argv"],
            ),
        ]

    def _list_files(self, arguments: dict[str, Any]) -> ToolResult:
        _reject_extra_arguments(arguments, {"path", "max_depth"})
        relative_path = arguments.get("path", ".")
        if not isinstance(relative_path, str):
            raise ToolValidationError("path 必须是字符串")
        max_depth = arguments.get("max_depth", 3)
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 1 <= max_depth <= 8:
            raise ToolValidationError("max_depth 必须是 1 到 8 的整数")

        base = self._resolve_path(relative_path, allow_workspace_root=True)
        if not base.is_dir():
            raise ToolValidationError(f"目录不存在: {relative_path}")

        entries: list[str] = []
        truncated = False
        for current, directory_names, file_names in os.walk(base, followlinks=False):
            current_path = Path(current)
            relative_current = current_path.relative_to(base)
            current_depth = 0 if relative_current == Path(".") else len(relative_current.parts)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name not in _IGNORED_DIRECTORIES and current_depth < max_depth
            )
            visible_names = sorted(directory_names + file_names)
            for item_name in visible_names:
                item_path = current_path / item_name
                item_depth = len(item_path.relative_to(base).parts)
                if item_depth > max_depth:
                    continue
                entries.append(item_path.relative_to(self.workspace).as_posix())
                if len(entries) > self.max_list_entries:
                    entries = entries[: self.max_list_entries]
                    truncated = True
                    break
            if truncated:
                break

        return ToolResult(_json({"entries": entries, "truncated": truncated}))

    def _read_file(self, arguments: dict[str, Any]) -> ToolResult:
        _reject_extra_arguments(arguments, {"path"})
        relative_path = _required_string(arguments, "path")
        target = self._resolve_path(relative_path)
        if not target.is_file():
            raise ToolValidationError(f"文件不存在或不是普通文件: {relative_path}")

        content = target.read_text(encoding="utf-8")
        return ToolResult(self._truncate(content))

    def _write_file(self, arguments: dict[str, Any]) -> ToolResult:
        _reject_extra_arguments(arguments, {"path", "content"})
        relative_path = _required_string(arguments, "path")
        content = _required_string(arguments, "content", allow_empty=True)
        if len(content) > self.max_write_chars:
            raise ToolValidationError(f"content 超过 {self.max_write_chars} 字符上限")

        target = self._resolve_path(relative_path)
        if target.exists() and target.is_dir():
            raise ToolValidationError(f"目标路径是目录: {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="")
        return ToolResult(
            _json(
                {
                    "path": target.relative_to(self.workspace).as_posix(),
                    "bytes_written": len(content.encode("utf-8")),
                }
            )
        )

    def _run_command(self, arguments: dict[str, Any]) -> ToolResult:
        _reject_extra_arguments(arguments, {"argv"})
        argv = arguments.get("argv")
        if not isinstance(argv, list) or not argv or len(argv) > 32:
            raise ToolValidationError("argv 必须是包含 1 到 32 项的字符串数组")
        if any(not isinstance(item, str) or not item or len(item) > 4_000 for item in argv):
            raise ToolValidationError("argv 每一项都必须是长度合理的非空字符串")

        try:
            completed = subprocess.run(
                argv,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                env=_command_environment(),
                timeout=self.command_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _timeout_stream(exc.stdout)
            stderr = _timeout_stream(exc.stderr)
            timeout_message = f"命令执行超时（{self.command_timeout_seconds:g} 秒）"
            stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message
            return ToolResult(
                _json(
                    {
                        "exit_code": None,
                        "stdout": self._truncate(stdout),
                        "stderr": self._truncate(stderr),
                        "timed_out": True,
                    }
                ),
                is_error=True,
            )
        except OSError as exc:
            return ToolResult(
                _json(
                    {
                        "exit_code": None,
                        "stdout": "",
                        "stderr": f"无法启动命令: {exc}",
                        "timed_out": False,
                    }
                ),
                is_error=True,
            )

        return ToolResult(
            _json(
                {
                    "exit_code": completed.returncode,
                    "stdout": self._truncate(completed.stdout),
                    "stderr": self._truncate(completed.stderr),
                    "timed_out": False,
                }
            ),
            is_error=completed.returncode != 0,
        )

    def _resolve_path(self, relative_path: str, *, allow_workspace_root: bool = False) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            raise ToolValidationError("path 必须是工作目录内的相对路径")
        if not relative_path or (not allow_workspace_root and path == Path(".")):
            raise ToolValidationError("path 必须指向工作目录内的具体文件或目录")

        target = (self.workspace / path).resolve()
        try:
            target.relative_to(self.workspace)
        except ValueError as exc:
            raise ToolValidationError("拒绝访问工作目录之外的路径") from exc
        return target

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        return text[: self.max_output_chars] + _TRUNCATION_MARKER


def _required_string(arguments: dict[str, Any], key: str, *, allow_empty: bool = False) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or (not allow_empty and not value):
        qualifier = "字符串" if allow_empty else "非空字符串"
        raise ToolValidationError(f"{key} 必须是{qualifier}")
    return value


def _reject_extra_arguments(arguments: dict[str, Any], allowed: set[str]) -> None:
    extras = set(arguments) - allowed
    if extras:
        raise ToolValidationError(f"不支持的工具参数: {', '.join(sorted(extras))}")


def _timeout_stream(stream: str | bytes | None) -> str:
    if stream is None:
        return ""
    if isinstance(stream, bytes):
        return stream.decode("utf-8", errors="replace")
    return stream


def _command_environment() -> dict[str, str]:
    """Keep normal process settings while withholding likely credentials."""
    return {
        name: value
        for name, value in os.environ.items()
        if not any(marker in name.upper() for marker in _SENSITIVE_ENV_MARKERS)
    }


def _function_schema(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)
