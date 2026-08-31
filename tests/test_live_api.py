import os

import pytest

from coding_agent.agent import Agent
from coding_agent.model import QwenClient
from coding_agent.tools import WorkspaceTools


pytestmark = pytest.mark.live


def test_real_qwen_agent_writes_and_verifies_file(tmp_path):
    if os.getenv("RUN_LIVE_API_TESTS") != "1":
        pytest.skip("set RUN_LIVE_API_TESTS=1 to call the real API")
    if not os.getenv("DASHSCOPE_BASE_URL"):
        pytest.skip("set DASHSCOPE_BASE_URL to the API Key's OpenAI-compatible URL")

    agent = Agent(QwenClient(), WorkspaceTools(tmp_path), max_rounds=6)
    result = agent.run(
        "Create hello.txt containing exactly hello, then read it to verify the "
        "content, and report completion."
    )

    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hello"
    assert 2 <= result.rounds <= 6
