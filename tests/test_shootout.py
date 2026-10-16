"""Tests for the model shootout script."""

import json
import pytest
from scripts.shootout import validate_schema, run_shootout, write_decision_record
import httpx


def test_validate_schema_valid():
    valid_data = {
        "stdout": "Linux web-prod-01 5.15.0-generic\n",
        "exit_code": 0,
        "state_changes": [
            {"op": "create_file", "path": "/tmp/test.txt", "content": "hello"}
        ],
    }
    assert validate_schema(valid_data) is True


def test_validate_schema_set_env():
    valid_env = {
        "stdout": "",
        "exit_code": 0,
        "state_changes": [
            {"op": "set_env", "path": "FOO", "content": "bar"}
        ],
    }
    assert validate_schema(valid_env) is True


def test_validate_schema_invalid():
    # Missing exit_code
    assert validate_schema({"stdout": "hi", "state_changes": []}) is False
    # Invalid op
    assert validate_schema({
        "stdout": "hi",
        "exit_code": 0,
        "state_changes": [{"op": "destroy_all", "path": "/"}]
    }) is False
    # Invalid path type
    assert validate_schema({
        "stdout": "hi",
        "exit_code": 0,
        "state_changes": [{"op": "create_file", "path": 123}]
    }) is False


def test_shootout_with_mock_client(tmp_path):
    # Mock Ollama chat endpoint
    def mock_handler(request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        prompt = data["messages"][-1]["content"]
        reply_content = json.dumps({
            "stdout": f"output of {prompt}\n",
            "exit_code": 0,
            "state_changes": []
        })
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": reply_content},
                "eval_count": 25,
                "eval_duration": 1_000_000_000,  # 1 second -> 25 tps
                "prompt_eval_duration": 100_000_000,  # 0.1s ttft
            }
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport, base_url="http://127.0.0.1:11434")

    res = run_shootout(
        model="qwen2.5:1.5b",
        prompts=["uname -a", "id"],
        client=client,
    )

    assert res["model"] == "qwen2.5:1.5b"
    assert res["prompts_tested"] == 2
    assert res["valid_json_count"] == 2
    assert res["schema_valid_rate"] == 1.0
    assert res["tokens_per_second"] == 25.0
    assert res["time_to_first_token_sec"] == 0.1

    # Verify decision record file write
    doc_path = tmp_path / "001-model.md"
    write_decision_record(res, filepath=str(doc_path))
    assert doc_path.exists()
    content = doc_path.read_text(encoding="utf-8")
    assert "ADR 001" in content
    assert "qwen2.5:1.5b" in content
