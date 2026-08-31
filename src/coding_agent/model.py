"""Small OpenAI-compatible Qwen client owned by this project."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from .errors import ModelAPIError, ModelConfigurationError, ModelResponseError


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass(frozen=True)
class ToolCall:
    """A validated function call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    """The normalized part of an assistant response used by the runtime."""

    content: str | None
    tool_calls: tuple[ToolCall, ...]
    assistant_message: dict[str, Any]


class QwenClient:
    """Call Qwen through its OpenAI-compatible HTTP endpoint."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "qwen3-coder-plus",
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self._api_key:
            raise ModelConfigurationError(
                "缺少 API Key：请设置 DASHSCOPE_API_KEY 环境变量。"
            )

        self._base_url = (
            base_url or os.getenv("DASHSCOPE_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        parsed_base_url = urlsplit(self._base_url)
        if (
            parsed_base_url.scheme != "https"
            or not parsed_base_url.hostname
            or parsed_base_url.username is not None
            or parsed_base_url.password is not None
        ):
            raise ModelConfigurationError(
                "模型 Base URL 必须是有效的 HTTPS 地址，且不能包含账号密码。"
            )
        self._model = model
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Literal["auto", "none"] = "auto",
    ) -> ModelResponse:
        """Send one completion request and validate its assistant message."""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice

        try:
            response = self._client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise ModelAPIError("模型 API 请求超时，请稍后重试。") from exc
        except httpx.RequestError as exc:
            raise ModelAPIError("无法连接模型 API，请检查网络和服务地址。") from exc

        if response.is_error:
            raise ModelAPIError(f"模型 API 返回 HTTP {response.status_code}。")

        try:
            body = response.json()
        except ValueError as exc:
            raise ModelResponseError("模型 API 返回的内容不是有效 JSON。") from exc

        return self._parse_response(body)

    @staticmethod
    def _parse_response(body: Any) -> ModelResponse:
        if not isinstance(body, dict):
            raise ModelResponseError("模型响应顶层必须是 JSON 对象。")

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelResponseError("模型响应缺少 choices。")

        choice = choices[0]
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            raise ModelResponseError("模型响应缺少 assistant message。")

        message = choice["message"]
        if message.get("role") != "assistant":
            raise ModelResponseError("模型消息角色不是 assistant。")

        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ModelResponseError("模型文本 content 类型无效。")

        raw_tool_calls = message.get("tool_calls", [])
        if not isinstance(raw_tool_calls, list):
            raise ModelResponseError("模型 tool_calls 类型无效。")

        tool_calls = tuple(QwenClient._parse_tool_call(item) for item in raw_tool_calls)
        if not content and not tool_calls:
            raise ModelResponseError("模型响应既没有文本，也没有工具调用。")

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            assistant_message=deepcopy(message),
        )

    @staticmethod
    def _parse_tool_call(item: Any) -> ToolCall:
        if not isinstance(item, dict) or item.get("type") != "function":
            raise ModelResponseError("工具调用结构无效。")

        call_id = item.get("id")
        function = item.get("function")
        if not isinstance(call_id, str) or not call_id or not isinstance(function, dict):
            raise ModelResponseError("工具调用缺少 id 或 function。")

        name = function.get("name")
        arguments_text = function.get("arguments")
        if not isinstance(name, str) or not name or not isinstance(arguments_text, str):
            raise ModelResponseError("工具调用缺少函数名或参数。")

        try:
            arguments = json.loads(arguments_text)
        except json.JSONDecodeError as exc:
            raise ModelResponseError(f"工具 {name} 的参数不是有效 JSON。") from exc
        if not isinstance(arguments, dict):
            raise ModelResponseError(f"工具 {name} 的参数必须是 JSON 对象。")

        return ToolCall(id=call_id, name=name, arguments=arguments)
