import io
import sys

from coding_agent.cli import build_parser, main
from coding_agent.errors import ModelConfigurationError
from coding_agent.model import ModelResponse, ToolCall


class ScriptedModel:
    def __init__(self, responses):
        self.responses = list(responses)

    def complete(self, messages, *, tools=None, tool_choice="auto"):
        return self.responses.pop(0)


def text_response(content):
    return ModelResponse(
        content=content,
        tool_calls=(),
        assistant_message={"role": "assistant", "content": content},
    )


def tool_response(call):
    return ModelResponse(
        content=None,
        tool_calls=(call,),
        assistant_message={
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": '{"path":"."}'},
                }
            ],
        },
    )


def test_parser_accepts_workspace_task_and_runtime_options(tmp_path):
    args = build_parser().parse_args(
        [
            "--workspace",
            str(tmp_path),
            "--model",
            "qwen-test",
            "--base-url",
            "https://example.invalid/v1",
            "--max-rounds",
            "3",
            "检查项目",
        ]
    )

    assert args.workspace == str(tmp_path)
    assert args.task == "检查项目"
    assert args.model == "qwen-test"
    assert args.base_url == "https://example.invalid/v1"
    assert args.max_rounds == 3


def test_main_runs_agent_and_displays_tool_progress(tmp_path, capsys):
    call = ToolCall(id="call_1", name="list_files", arguments={"path": "."})
    scripted = ScriptedModel([tool_response(call), text_response("检查完成")])
    factory_arguments = {}

    def client_factory(**kwargs):
        factory_arguments.update(kwargs)
        return scripted

    exit_code = main(
        ["--workspace", str(tmp_path), "--max-rounds", "2", "列出文件"],
        client_factory=client_factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "第 1 轮" in captured.out
    assert "list_files" in captured.out
    assert '"path": "."' in captured.out
    assert "成功" in captured.out
    assert "正在生成最终总结" in captured.out
    assert "检查完成" in captured.out
    assert captured.err == ""
    assert factory_arguments == {
        "base_url": None,
        "model": "qwen3-coder-plus",
    }


def test_main_reports_controlled_configuration_error(tmp_path, capsys):
    def client_factory(**kwargs):
        raise ModelConfigurationError("缺少测试密钥")

    exit_code = main(
        ["--workspace", str(tmp_path), "执行任务"],
        client_factory=client_factory,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "错误" in captured.err
    assert "缺少测试密钥" in captured.err
    assert "Traceback" not in captured.err


def test_main_reports_invalid_workspace(capsys, tmp_path):
    exit_code = main(
        ["--workspace", str(tmp_path / "missing"), "执行任务"],
        client_factory=lambda **kwargs: ScriptedModel([]),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "工作目录" in captured.err


def test_main_does_not_crash_when_console_cannot_encode_model_emoji(
    tmp_path, monkeypatch
):
    model = ScriptedModel([text_response("任务完成 ✅")])
    output_bytes = io.BytesIO()
    narrow_console = io.TextIOWrapper(
        output_bytes,
        encoding="gbk",
        errors="strict",
    )
    monkeypatch.setattr(sys, "stdout", narrow_console)

    exit_code = main(
        ["--workspace", str(tmp_path), "执行任务"],
        client_factory=lambda **kwargs: model,
    )
    narrow_console.flush()
    rendered = output_bytes.getvalue().decode("gbk")

    assert exit_code == 0
    assert "任务完成" in rendered
