"""Baseline mode tests with a fake HTTP client (no Ollama needed)."""
import json

import pytest

pytest.importorskip("bench.checkers", reason="bench playbooks/checkers not merged yet")
pytest.importorskip("canarynet.llm.adapter", reason="adapter.py not merged yet")

from bench import baseline  # noqa: E402
from canarynet.llm import adapter  # noqa: E402


class FakeResponse:
    def __init__(self, status, content):
        self.status_code = status
        self._content = content

    def json(self):
        return {"message": {"content": self._content}}


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def post(self, url, json=None):
        self.calls.append((url, json))
        status, content = self.replies.pop(0) if self.replies else (200, '{"stdout": "x", "exit_code": 0}')
        return FakeResponse(status, content)


def _ok(stdout, code=0):
    return 200, json.dumps({"stdout": stdout, "exit_code": code, "state_changes": []})


def test_same_model_persona_schema_and_loopback_url():
    client = FakeClient([_ok("admin")])
    baseline.run_playbook_baseline("p", ["whoami"], client)
    url, payload = client.calls[0]
    assert url == adapter.OLLAMA_CHAT_URL and url.startswith("http://127.0.0.1:11434/")
    assert payload["model"] == adapter.DEFAULT_MODEL
    assert payload["messages"][0]["content"] == adapter.SYSTEM_PERSONA
    assert payload["format"] == adapter.SCHEMA


def test_only_last_ten_commands_are_remembered():
    cmds = [f"echo step{i:02d}" for i in range(12)]
    client = FakeClient([_ok(f"step{i:02d}") for i in range(12)])
    baseline.run_playbook_baseline("p", cmds, client)
    last_prompt = client.calls[-1][1]["messages"][1]["content"]
    history_part = last_prompt.split("Visitor Input:")[0]
    assert "echo step00" not in history_part
    assert "echo step01" in history_part and "echo step10" in history_part


def test_never_answered_by_code_and_failures_are_not_found():
    client = FakeClient([_ok("admin"), (500, ""), (200, "not json"), (200, '{"stdout": 5}')])
    trace, lats = baseline.run_playbook_baseline("p", ["whoami", "id", "uname -a", "ls"], client)
    assert [s.answered_by for s in trace] == ["model", "not_found", "not_found", "not_found"]
    assert trace[0].stdout == "admin\n"
    assert trace[1].stdout == "bash: id: command not found\n" and trace[1].exit_code == 127
    assert len(lats) == 4 and all(x >= 0 for x in lats)


def test_state_changed_is_lenient_for_mutating_commands():
    client = FakeClient([_ok("")] * 4)
    trace, _ = baseline.run_playbook_baseline(
        "p", ["cd /tmp", "echo hi > a", "cat a", "pwd"], client)
    assert [s.state_changed for s in trace] == [True, True, False, False]
