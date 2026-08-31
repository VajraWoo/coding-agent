from pathlib import Path

import pytest

from coding_agent.policy import ApprovalRequest, PolicyTools
from coding_agent.tools import WorkspaceTools


def schema_names(tools: PolicyTools) -> set[str]:
    return {item["function"]["name"] for item in tools.schemas()}


def test_ask_mode_exposes_only_read_tools(tmp_path: Path) -> None:
    tools = PolicyTools(WorkspaceTools(tmp_path), mode="ask")

    assert schema_names(tools) == {"list_files", "read_file"}


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("write_file", {"path": "blocked.txt", "content": "no"}),
        ("run_command", {"argv": ["python", "-c", "print('no')"]}),
    ],
)
def test_ask_mode_rejects_side_effect_tools_even_if_model_forges_call(
    tmp_path: Path, tool_name: str, arguments: dict
) -> None:
    tools = PolicyTools(WorkspaceTools(tmp_path), mode="ask")

    result = tools.execute(tool_name, arguments)

    assert result.is_error is True
    assert "只读" in result.content
    assert not (tmp_path / "blocked.txt").exists()


def test_develop_mode_passes_exact_write_request_to_approver(tmp_path: Path) -> None:
    approvals: list[ApprovalRequest] = []

    def approve(request: ApprovalRequest) -> bool:
        approvals.append(request)
        return True

    tools = PolicyTools(
        WorkspaceTools(tmp_path),
        mode="develop",
        approve=approve,
    )

    result = tools.execute(
        "write_file",
        {"path": "approved.txt", "content": "yes"},
    )

    assert result.is_error is False
    assert approvals == [
        ApprovalRequest(
            tool_name="write_file",
            arguments={"path": "approved.txt", "content": "yes"},
        )
    ]
    assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == "yes"


def test_develop_mode_denial_becomes_tool_error_without_side_effect(
    tmp_path: Path,
) -> None:
    tools = PolicyTools(
        WorkspaceTools(tmp_path),
        mode="develop",
        approve=lambda request: False,
    )

    result = tools.execute(
        "write_file",
        {"path": "denied.txt", "content": "no"},
    )

    assert result.is_error is True
    assert "拒绝" in result.content
    assert not (tmp_path / "denied.txt").exists()


def test_develop_mode_requires_approval_configuration_for_side_effect(
    tmp_path: Path,
) -> None:
    tools = PolicyTools(WorkspaceTools(tmp_path), mode="develop")

    result = tools.execute(
        "write_file",
        {"path": "missing-approval.txt", "content": "no"},
    )

    assert result.is_error is True
    assert "批准" in result.content
    assert not (tmp_path / "missing-approval.txt").exists()


def test_read_tools_do_not_request_approval(tmp_path: Path) -> None:
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    approvals: list[ApprovalRequest] = []
    tools = PolicyTools(
        WorkspaceTools(tmp_path),
        mode="develop",
        approve=lambda request: approvals.append(request) or True,
    )

    result = tools.execute("read_file", {"path": "note.txt"})

    assert result.content == "hello"
    assert approvals == []


def test_auto_approve_development_session_does_not_call_approver(
    tmp_path: Path,
) -> None:
    tools = PolicyTools(
        WorkspaceTools(tmp_path),
        mode="develop",
        approve=lambda request: pytest.fail("approver should not be called"),
        auto_approve=True,
    )

    result = tools.execute(
        "write_file",
        {"path": "automatic.txt", "content": "ok"},
    )

    assert result.is_error is False
    assert (tmp_path / "automatic.txt").exists()


@pytest.mark.parametrize("mode", ["", "write", None, 123])
def test_rejects_unknown_policy_mode(tmp_path: Path, mode) -> None:
    with pytest.raises(ValueError, match="mode"):
        PolicyTools(WorkspaceTools(tmp_path), mode=mode)
