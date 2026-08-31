from copy import deepcopy

import pytest

from coding_agent.agent import Agent, AgentEvent
from coding_agent.errors import AgentLimitError
from coding_agent.model import ModelResponse, ToolCall
from coding_agent.tools import ToolResult


def text_response(content="完成"):
    message = {"role": "assistant", "content": content}
    return ModelResponse(content=content, tool_calls=(), assistant_message=message)


def tool_response(*calls):
    raw_calls = [
        {
            "id": call.id,
            "type": "function",
            "function": {"name": call.name, "arguments": "{}"},
        }
        for call in calls
    ]
    message = {"role": "assistant", "content": None, "tool_calls": raw_calls}
    return ModelResponse(content=None, tool_calls=tuple(calls), assistant_message=message)


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, messages, *, tools=None):
        self.requests.append({"messages": deepcopy(messages), "tools": deepcopy(tools)})
        if not self.responses:
            raise AssertionError("模型被调用次数超过测试脚本")
        return self.responses.pop(0)


class StubTools:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def schemas(self):
        return [{"type": "function", "function": {"name": "demo_tool"}}]

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        if self.results:
            return self.results.pop(0)
        return ToolResult("ok")


def test_returns_immediate_text_and_builds_initial_history():
    model = ScriptedModel([text_response("已经检查完成")])
    tools = StubTools()
    agent = Agent(model, tools, system_prompt="系统规则")

    result = agent.run("检查项目")

    assert result.final_text == "已经检查完成"
    assert result.rounds == 1
    assert result.history == (
        {"role": "system", "content": "系统规则"},
        {"role": "user", "content": "检查项目"},
        {"role": "assistant", "content": "已经检查完成"},
    )
    assert model.requests[0]["tools"] == tools.schemas()


def test_executes_tool_and_sends_observation_back_to_model():
    call = ToolCall(id="call_1", name="demo_tool", arguments={"path": "a.txt"})
    model = ScriptedModel([tool_response(call), text_response("文件已读取")])
    tools = StubTools([ToolResult("文件内容")])

    result = Agent(model, tools).run("读取文件")

    assert result.rounds == 2
    assert tools.calls == [("demo_tool", {"path": "a.txt"})]
    second_history = model.requests[1]["messages"]
    assert second_history[-2]["role"] == "assistant"
    assert second_history[-2]["tool_calls"][0]["id"] == "call_1"
    assert second_history[-1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"content": "文件内容", "is_error": false}',
    }
    assert result.history[-1] == {"role": "assistant", "content": "文件已读取"}


def test_executes_all_tool_calls_in_model_order():
    first = ToolCall(id="call_1", name="first", arguments={"n": 1})
    second = ToolCall(id="call_2", name="second", arguments={"n": 2})
    model = ScriptedModel([tool_response(first, second), text_response()])
    tools = StubTools([ToolResult("one"), ToolResult("two", is_error=True)])

    result = Agent(model, tools).run("调用两个工具")

    assert tools.calls == [("first", {"n": 1}), ("second", {"n": 2})]
    tool_messages = [message for message in result.history if message["role"] == "tool"]
    assert [message["tool_call_id"] for message in tool_messages] == ["call_1", "call_2"]
    assert '"is_error": true' in tool_messages[1]["content"]


def test_tool_error_is_feedback_not_runtime_crash():
    call = ToolCall(id="bad", name="missing_tool", arguments={})
    model = ScriptedModel([tool_response(call), text_response("已改用其他方案")])
    tools = StubTools([ToolResult("未知工具", is_error=True)])

    result = Agent(model, tools).run("完成任务")

    assert result.final_text == "已改用其他方案"
    assert '"is_error": true' in model.requests[1]["messages"][-1]["content"]


def test_stops_after_maximum_model_rounds():
    calls = [ToolCall(id=f"call_{i}", name="demo_tool", arguments={}) for i in range(2)]
    model = ScriptedModel([tool_response(call) for call in calls])
    tools = StubTools()

    with pytest.raises(AgentLimitError, match="2"):
        Agent(model, tools, max_rounds=2).run("永不结束的任务")

    assert len(model.requests) == 2
    assert len(tools.calls) == 2


@pytest.mark.parametrize("task", ["", "   ", None, 123])
def test_rejects_invalid_task(task):
    with pytest.raises(ValueError, match="任务"):
        Agent(ScriptedModel([]), StubTools()).run(task)


def test_emits_events_for_observable_progress():
    call = ToolCall(id="call_1", name="demo_tool", arguments={})
    model = ScriptedModel([tool_response(call), text_response("结束")])
    tools = StubTools([ToolResult("观察")])
    events: list[AgentEvent] = []

    Agent(model, tools).run("执行", on_event=events.append)

    assert [event.kind for event in events] == [
        "model_request",
        "tool_call",
        "tool_result",
        "model_request",
        "final",
    ]
    assert events[1].tool_name == "demo_tool"
    assert events[2].is_error is False
    assert events[-1].message == "结束"
