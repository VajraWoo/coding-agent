"""Command-line interface for the minimal coding agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

from .agent import Agent, AgentEvent
from .errors import AgentError, ModelError
from .model import QwenClient
from .tools import WorkspaceTools


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="coding-agent",
        description="在指定工作目录中运行一个最小编程智能体",
    )
    parser.add_argument("task", help="要交给 Agent 的自然语言编程任务")
    parser.add_argument(
        "--workspace",
        required=True,
        help="Agent 可以操作的工作目录",
    )
    parser.add_argument(
        "--model",
        default="qwen3-coder-plus",
        help="百炼模型名称（默认: qwen3-coder-plus）",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI 兼容 Base URL；也可设置 DASHSCOPE_BASE_URL",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=12,
        help="最大模型调用轮数（默认: 12）",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[..., Any] = QwenClient,
) -> int:
    """Run the CLI and return a process exit code."""
    _configure_console_output()
    args = build_parser().parse_args(argv)

    try:
        tools = WorkspaceTools(Path(args.workspace))
        model = client_factory(base_url=args.base_url, model=args.model)
        agent = Agent(model, tools, max_rounds=args.max_rounds)
        agent.run(args.task, on_event=_print_event)
    except (ModelError, AgentError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已由用户中止。", file=sys.stderr)
        return 130

    return 0


def _print_event(event: AgentEvent) -> None:
    if event.kind == "model_request":
        print(f"[第 {event.round_number} 轮] {event.message}...")
    elif event.kind == "tool_call":
        arguments = json.dumps(event.arguments or {}, ensure_ascii=False)
        print(f"[工具] {event.tool_name} {arguments}")
    elif event.kind == "tool_result":
        status = "失败" if event.is_error else "成功"
        print(f"[结果/{status}] {_preview(event.message)}")
    elif event.kind == "final":
        print(f"\nAgent 最终回答:\n{event.message}")


def _preview(text: str, limit: int = 500) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[终端显示已省略，完整结果仍已反馈给模型]"


def _configure_console_output() -> None:
    """Replace characters unsupported by a legacy Windows console encoding."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="replace")
            except (OSError, ValueError):
                pass


def entrypoint() -> None:
    raise SystemExit(main())
