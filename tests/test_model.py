import json

import httpx
import pytest

from coding_agent.errors import ModelAPIError, ModelConfigurationError, ModelResponseError
from coding_agent.model import QwenClient


BASE_URL = "https://example.invalid/compatible-mode/v1"


def make_client(handler, *, api_key="test-secret"):
    return QwenClient(
        api_key=api_key,
        base_url=BASE_URL,
        transport=httpx.MockTransport(handler),
    )


def json_response(payload, status_code=200):
    return httpx.Response(status_code, json=payload)


def test_missing_api_key_fails_before_sending_request(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    with pytest.raises(ModelConfigurationError, match="DASHSCOPE_API_KEY"):
        QwenClient(api_key=None, base_url=BASE_URL)


def test_rejects_plain_http_base_url_before_sending_secret():
    with pytest.raises(ModelConfigurationError, match="HTTPS"):
        QwenClient(api_key="test-secret", base_url="http://example.com/v1")


def test_sends_openai_compatible_request_and_parses_text_response():
    captured = {}

    def handler(request):
        captured["request"] = request
        captured["body"] = json.loads(request.content)
        return json_response(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": "任务完成"}}
                ]
            }
        )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "读取文件",
                "parameters": {"type": "object"},
            },
        }
    ]
    client = make_client(handler)

    result = client.complete(
        [{"role": "user", "content": "检查项目"}],
        tools=tools,
    )

    assert captured["request"].url == f"{BASE_URL}/chat/completions"
    assert captured["request"].headers["authorization"] == "Bearer test-secret"
    assert captured["body"] == {
        "model": "qwen3-coder-plus",
        "messages": [{"role": "user", "content": "检查项目"}],
        "tools": tools,
        "tool_choice": "auto",
    }
    assert result.content == "任务完成"
    assert result.tool_calls == ()
    assert result.assistant_message == {"role": "assistant", "content": "任务完成"}


def test_parses_multiple_tool_calls_and_preserves_assistant_message():
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path":"README.md"}',
                },
            },
            {
                "id": "call_2",
                "type": "function",
                "function": {
                    "name": "run_command",
                    "arguments": '{"command":["python","-m","pytest"]}',
                },
            },
        ],
    }

    client = make_client(lambda request: json_response({"choices": [{"message": message}]}))
    result = client.complete([{"role": "user", "content": "运行测试"}])

    assert [call.id for call in result.tool_calls] == ["call_1", "call_2"]
    assert result.tool_calls[0].name == "read_file"
    assert result.tool_calls[0].arguments == {"path": "README.md"}
    assert result.tool_calls[1].arguments == {"command": ["python", "-m", "pytest"]}
    assert result.assistant_message == message


@pytest.mark.parametrize(
    "message",
    [
        {"role": "assistant", "content": None},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "not-json"},
                }
            ],
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "[]"},
                }
            ],
        },
    ],
)
def test_rejects_malformed_assistant_messages(message):
    client = make_client(lambda request: json_response({"choices": [{"message": message}]}))

    with pytest.raises(ModelResponseError):
        client.complete([{"role": "user", "content": "test"}])


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": [{}]}])
def test_rejects_malformed_response_envelope(payload):
    client = make_client(lambda request: json_response(payload))

    with pytest.raises(ModelResponseError):
        client.complete([{"role": "user", "content": "test"}])


@pytest.mark.parametrize("status_code", [401, 429, 500])
def test_http_errors_are_controlled_and_do_not_leak_api_key(status_code):
    secret = "never-print-this-key"
    client = make_client(
        lambda request: json_response({"error": {"message": "request failed"}}, status_code),
        api_key=secret,
    )

    with pytest.raises(ModelAPIError) as exc_info:
        client.complete([{"role": "user", "content": "test"}])

    assert str(status_code) in str(exc_info.value)
    assert secret not in str(exc_info.value)


def test_timeout_is_reported_as_controlled_api_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    client = make_client(handler)

    with pytest.raises(ModelAPIError, match="超时"):
        client.complete([{"role": "user", "content": "test"}])


def test_invalid_json_response_is_rejected():
    client = make_client(
        lambda request: httpx.Response(
            200,
            content=b"not-json",
            headers={"content-type": "text/plain"},
        )
    )

    with pytest.raises(ModelResponseError, match="JSON"):
        client.complete([{"role": "user", "content": "test"}])
