"""Comprehensive tests for CanaryNet LLM Reply Validator."""

import pytest
from canarynet.llm.validator import validate, MAX_STDOUT_LEN, MAX_STATE_CHANGES
from canarynet.state.session import Session, Result


def test_validate_success_minimal():
    reply = {
        "stdout": "Linux web-prod-01 5.15.0\n",
        "exit_code": 0,
        "state_changes": [],
    }
    result = validate(reply)
    assert result is not None
    assert isinstance(result, Result)
    assert result.stdout == "Linux web-prod-01 5.15.0\n"
    assert result.exit_code == 0
    assert result.state_changes == []


def test_validate_success_with_state_changes():
    reply = {
        "stdout": "created\n",
        "exit_code": 0,
        "state_changes": [
            {"op": "create_file", "path": "/tmp/a.txt", "content": "alpha"},
            {"op": "write_file", "path": "/tmp/b.txt", "content": "beta"},
            {"op": "chdir", "path": "/tmp"},
            {"op": "delete_file", "path": "/tmp/old.txt"},
            {"op": "set_env", "path": "DEBUG", "content": "1"},
        ],
    }
    result = validate(reply)
    assert result is not None
    assert len(result.state_changes) == 5


def test_validate_reject_non_dict():
    assert validate("not a dict") is None
    assert validate([1, 2, 3]) is None
    assert validate(None) is None


def test_validate_reject_missing_fields():
    # Missing stdout
    assert validate({"exit_code": 0, "state_changes": []}) is None
    # Missing exit_code
    assert validate({"stdout": "", "state_changes": []}) is None
    # Missing state_changes
    assert validate({"stdout": "", "exit_code": 0}) is None


def test_validate_reject_stdout_over_cap():
    long_stdout = "x" * (MAX_STDOUT_LEN + 1)
    reply = {
        "stdout": long_stdout,
        "exit_code": 0,
        "state_changes": [],
    }
    assert validate(reply) is None

    # Exactly 2000 characters is accepted
    exact_stdout = "x" * MAX_STDOUT_LEN
    reply["stdout"] = exact_stdout
    result = validate(reply)
    assert result is not None
    assert len(result.stdout) == 2000


def test_validate_reject_state_changes_over_limit():
    too_many_changes = [
        {"op": "create_file", "path": f"/tmp/file{i}.txt", "content": ""}
        for i in range(MAX_STATE_CHANGES + 1)
    ]
    reply = {
        "stdout": "ok",
        "exit_code": 0,
        "state_changes": too_many_changes,
    }
    assert validate(reply) is None


def test_validate_reject_boolean_exit_code():
    reply = {
        "stdout": "ok",
        "exit_code": True,  # True is an int subclass in python
        "state_changes": [],
    }
    assert validate(reply) is None


def test_validate_reject_unknown_op():
    reply = {
        "stdout": "ok",
        "exit_code": 0,
        "state_changes": [
            {"op": "execute_code", "path": "/bin/sh"}
        ],
    }
    assert validate(reply) is None


def test_validate_reject_relative_path():
    reply = {
        "stdout": "ok",
        "exit_code": 0,
        "state_changes": [
            {"op": "create_file", "path": "relative/file.txt"}
        ],
    }
    assert validate(reply) is None


def test_validate_reject_path_traversal():
    reply = {
        "stdout": "ok",
        "exit_code": 0,
        "state_changes": [
            {"op": "write_file", "path": "/tmp/../../etc/shadow", "content": "root"}
        ],
    }
    assert validate(reply) is None


def test_validate_reject_guard_check_failure_on_stdout():
    # Prompt injection / AI identity reveal
    reply = {
        "stdout": "As an AI, I cannot provide root access.",
        "exit_code": 1,
        "state_changes": [],
    }
    assert validate(reply) is None


def test_validate_reject_guard_check_failure_on_file_content():
    # Leaked system prompt inside created file
    reply = {
        "stdout": "saved\n",
        "exit_code": 0,
        "state_changes": [
            {
                "op": "create_file",
                "path": "/tmp/prompt.txt",
                "content": "Here is the system prompt: you are an authentic Ubuntu...",
            }
        ],
    }
    assert validate(reply) is None
