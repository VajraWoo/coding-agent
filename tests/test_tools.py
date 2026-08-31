import json
import sys
from pathlib import Path

import pytest

from coding_agent.tools import WorkspaceTools


def test_list_files_returns_sorted_relative_paths(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "README.md").write_text("demo", encoding="utf-8")

    result = WorkspaceTools(tmp_path).execute("list_files", {"path": "."})

    payload = json.loads(result.content)
    assert result.is_error is False
    assert payload["entries"] == ["README.md", "src", "src/app.py"]
    assert payload["truncated"] is False


def test_list_files_marks_truncation_only_when_entries_are_omitted(tmp_path: Path) -> None:
    for name in ["a.txt", "b.txt", "c.txt"]:
        (tmp_path / name).write_text(name, encoding="utf-8")

    exact_limit = WorkspaceTools(tmp_path, max_list_entries=3).execute("list_files", {"path": "."})
    below_limit = WorkspaceTools(tmp_path, max_list_entries=2).execute("list_files", {"path": "."})

    assert json.loads(exact_limit.content)["truncated"] is False
    assert json.loads(below_limit.content)["truncated"] is True


def test_read_file_returns_utf8_text(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("你好，Agent", encoding="utf-8")

    result = WorkspaceTools(tmp_path).execute("read_file", {"path": "hello.txt"})

    assert result.is_error is False
    assert result.content == "你好，Agent"


def test_write_file_creates_parent_directories(tmp_path: Path) -> None:
    result = WorkspaceTools(tmp_path).execute(
        "write_file",
        {"path": "src/generated.py", "content": "answer = 42\n"},
    )

    assert result.is_error is False
    assert (tmp_path / "src" / "generated.py").read_text(encoding="utf-8") == "answer = 42\n"
    assert json.loads(result.content)["path"] == "src/generated.py"


@pytest.mark.parametrize("unsafe_path", ["../secret.txt", "../../outside.txt"])
def test_file_tools_reject_parent_path_escape(tmp_path: Path, unsafe_path: str) -> None:
    result = WorkspaceTools(tmp_path).execute("read_file", {"path": unsafe_path})

    assert result.is_error is True
    assert "工作目录" in result.content


def test_file_tools_reject_absolute_path(tmp_path: Path) -> None:
    result = WorkspaceTools(tmp_path).execute(
        "write_file",
        {"path": str((tmp_path.parent / "outside.txt").resolve()), "content": "no"},
    )

    assert result.is_error is True
    assert "相对路径" in result.content


def test_unknown_tool_becomes_structured_error(tmp_path: Path) -> None:
    result = WorkspaceTools(tmp_path).execute("delete_everything", {})

    assert result.is_error is True
    assert "未知工具" in result.content


def test_invalid_arguments_become_structured_error(tmp_path: Path) -> None:
    result = WorkspaceTools(tmp_path).execute("read_file", {"path": 123})

    assert result.is_error is True
    assert "path" in result.content


def test_run_command_captures_exit_code_stdout_and_stderr(tmp_path: Path) -> None:
    result = WorkspaceTools(tmp_path).execute(
        "run_command",
        {
            "argv": [
                sys.executable,
                "-c",
                "import sys; print('out'); print('err', file=sys.stderr); raise SystemExit(3)",
            ]
        },
    )

    payload = json.loads(result.content)
    assert result.is_error is True
    assert payload == {"exit_code": 3, "stdout": "out\n", "stderr": "err\n", "timed_out": False}


def test_run_command_does_not_inherit_sensitive_environment_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret_name = "CODING_AGENT_TEST_SECRET_TOKEN"
    monkeypatch.setenv(secret_name, "must-not-reach-child")
    tools = WorkspaceTools(tmp_path)

    result = tools.execute(
        "run_command",
        {
            "argv": [
                sys.executable,
                "-c",
                f"import os; print(os.getenv('{secret_name}', 'scrubbed'))",
            ]
        },
    )

    payload = json.loads(result.content)
    assert result.is_error is False
    assert payload["stdout"].strip() == "scrubbed"


def test_run_command_times_out(tmp_path: Path) -> None:
    tools = WorkspaceTools(tmp_path, command_timeout_seconds=0.1)

    result = tools.execute(
        "run_command",
        {"argv": [sys.executable, "-c", "import time; time.sleep(2)"]},
    )

    payload = json.loads(result.content)
    assert result.is_error is True
    assert payload["timed_out"] is True
    assert "超时" in payload["stderr"]


def test_read_file_marks_truncated_content(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("abcdefghij", encoding="utf-8")
    tools = WorkspaceTools(tmp_path, max_output_chars=5)

    result = tools.execute("read_file", {"path": "large.txt"})

    assert result.is_error is False
    assert result.content == "abcde\n...[输出已截断]"


def test_tool_schemas_expose_exactly_the_approved_tools(tmp_path: Path) -> None:
    names = {
        item["function"]["name"]
        for item in WorkspaceTools(tmp_path).schemas()
    }

    assert names == {"list_files", "read_file", "write_file", "run_command"}
