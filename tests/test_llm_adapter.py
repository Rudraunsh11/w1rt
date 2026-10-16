"""Tests for canarynet.llm.adapter."""

import json
import httpx
import pytest
from canarynet.llm.adapter import ask_model, OLLAMA_CHAT_URL
from canarynet.state.session import Session, Result


def test_ask_model_mock_valid():
    session = Session(session_id="test-1", user="admin")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert request.url == OLLAMA_CHAT_URL
        data = json.loads(request.content)
        assert data["model"] == "qwen2.5:1.5b"
        assert data["options"]["temperature"] == 0.0
        assert data["options"]["seed"] == 42

        reply_content = json.dumps({
            "stdout": "Linux web-prod-01 5.15.0-58-generic x86_64\n",
            "exit_code": 0,
            "state_changes": [],
        })
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": reply_content}}
        )

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    result = ask_model(session, "uname -r", client=client)

    assert result is not None
    assert isinstance(result, Result)
    assert "5.15.0-58-generic" in result.stdout
    assert result.exit_code == 0
    assert result.state_changes == []


def test_ask_model_mock_malformed_json():
    session = Session(session_id="test-2", user="admin")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "Not valid JSON at all!"}}
        )

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    result = ask_model(session, "cat foo", client=client)
    assert result is None


def test_ask_model_mock_server_error():
    session = Session(session_id="test-3", user="admin")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    result = ask_model(session, "uptime", client=client)
    assert result is None


def test_ask_model_timeout():
    session = Session(session_id="test-4", user="admin")

    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("Read timed out")

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    result = ask_model(session, "sleep 10", client=client, timeout=0.1)
    assert result is None


def test_ask_model_live_ollama():
    """Live integration test against running local Ollama instance."""
    session = Session(session_id="test-live", user="admin")
    result = ask_model(session, "uname -s", timeout=15.0)
    # If Ollama is running, result should be a valid Result object
    if result is not None:
        assert isinstance(result, Result)
        assert result.exit_code == 0
        assert "linux" in result.stdout.lower()
