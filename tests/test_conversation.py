from copy import deepcopy
from threading import Event, Thread

import pytest

from coding_agent.agent import Agent
from coding_agent.conversation import Conversation
from coding_agent.errors import ConversationBusyError, ModelAPIError
from coding_agent.model import ModelResponse


def text_response(content: str) -> ModelResponse:
    return ModelResponse(
        content=content,
        tool_calls=(),
        assistant_message={"role": "assistant", "content": content},
    )


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def complete(self, messages, *, tools=None, tool_choice="auto"):
        self.requests.append(deepcopy(messages))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class EmptyTools:
    def schemas(self):
        return []

    def execute(self, name, arguments):
        raise AssertionError("no tool call expected")


def test_second_message_receives_complete_first_turn_history():
    model = ScriptedModel([text_response("第一答"), text_response("第二答")])
    conversation = Conversation(Agent(model, EmptyTools(), system_prompt="规则"))

    first = conversation.send("第一问")
    second = conversation.send("继续追问")

    assert first.final_text == "第一答"
    assert second.final_text == "第二答"
    assert model.requests[1] == [
        {"role": "system", "content": "规则"},
        {"role": "user", "content": "第一问"},
        {"role": "assistant", "content": "第一答"},
        {"role": "user", "content": "继续追问"},
    ]
    assert [message["role"] for message in conversation.history] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_exposed_history_is_a_copy():
    model = ScriptedModel([text_response("回答")])
    conversation = Conversation(Agent(model, EmptyTools()))
    conversation.send("问题")

    exposed = conversation.history
    exposed[-1]["content"] = "外部篡改"

    assert conversation.history[-1]["content"] == "回答"


def test_failed_follow_up_keeps_last_successful_history():
    model = ScriptedModel(
        [text_response("第一答"), ModelAPIError("临时失败"), text_response("恢复")]
    )
    conversation = Conversation(Agent(model, EmptyTools()))
    conversation.send("第一问")
    before_failure = conversation.history

    with pytest.raises(ModelAPIError, match="临时失败"):
        conversation.send("失败的问题")

    assert conversation.history == before_failure
    result = conversation.send("重新提问")
    assert result.final_text == "恢复"
    assert all(message.get("content") != "失败的问题" for message in model.requests[-1])


def test_rejects_concurrent_message_while_model_is_running():
    entered = Event()
    release = Event()

    class BlockingModel:
        def complete(self, messages, *, tools=None, tool_choice="auto"):
            entered.set()
            assert release.wait(timeout=2)
            return text_response("完成")

    conversation = Conversation(Agent(BlockingModel(), EmptyTools()))
    background_error = []

    def send_first():
        try:
            conversation.send("耗时问题")
        except Exception as exc:  # pragma: no cover - diagnostic capture
            background_error.append(exc)

    thread = Thread(target=send_first)
    thread.start()
    assert entered.wait(timeout=2)

    with pytest.raises(ConversationBusyError, match="运行"):
        conversation.send("同时发来的问题")

    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert background_error == []


def test_reset_discards_previous_turns():
    model = ScriptedModel([text_response("一"), text_response("二")])
    conversation = Conversation(Agent(model, EmptyTools(), system_prompt="规则"))
    conversation.send("旧问题")

    conversation.reset()
    conversation.send("新问题")

    assert model.requests[-1] == [
        {"role": "system", "content": "规则"},
        {"role": "user", "content": "新问题"},
    ]
