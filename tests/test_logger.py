"""Behavior checks for the public logging contract."""

import json
import os
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from datetime import datetime, timedelta

import pytest

from canarynet.logger import log_event


def read_events(directory):
    lines = (directory / "logs/events.jsonl").read_text(encoding="utf-8").splitlines()
    return lines, [json.loads(line) for line in lines]


def _process_writer(directory, worker):
    os.chdir(directory)
    for i in range(30):
        log_event(str(worker), "127.0.0.1", str(i), "x\n" * 10000, "code", 0, [])


def test_creates_directory_and_preserves_contract_fields(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = log_event("session-1", "127.0.0.1", "ls", "notes\n", "code", 1.25, ["T1083"])
    lines, events = read_events(tmp_path)
    assert result is None
    assert len(lines) == 1
    event = events[0]
    assert set(event) == {
        "session_id", "src", "input", "output", "answered_by", "latency_ms", "tags", "timestamp"
    }
    timestamp = datetime.fromisoformat(event.pop("timestamp").replace("Z", "+00:00"))
    assert timestamp.utcoffset() == timedelta(0)
    assert event == {
        "session_id": "session-1", "src": "127.0.0.1", "input": "ls",
        "output": "notes\n", "answered_by": "code", "latency_ms": 1.25,
        "tags": ["T1083"],
    }


def test_newlines_quotes_and_unicode_stay_in_one_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    text = 'hello\n{"forged": true}\r\n"quoted"\\ café नमस्ते'
    log_event("s", "127.0.0.1", text, text, "model", 0, [])
    log_event("s", "127.0.0.1", "pwd", "/home/admin", "code", 0, [])
    lines, events = read_events(tmp_path)
    assert len(lines) == 2
    assert events[0]["input"] == text
    assert events[0]["output"] == text
    assert events[1]["input"] == "pwd"


def test_concurrent_threads_lose_no_records(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def append(number):
        log_event("s", "127.0.0.1", str(number), "x\n" * 1000, "code", 0, [])
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(append, range(180)))
    lines, events = read_events(tmp_path)
    assert len(lines) == 180
    assert {event["input"] for event in events} == {str(i) for i in range(180)}
    assert all(event["output"] == "x\n" * 1000 for event in events)


def test_concurrent_processes_lose_no_records(tmp_path):
    # Workers run a fixed developer-written function, never visitor commands.
    with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [pool.submit(_process_writer, str(tmp_path), worker) for worker in range(4)]
        for future in futures:
            future.result(timeout=20)
    lines, events = read_events(tmp_path)
    assert len(lines) == 120
    assert {(event["session_id"], event["input"]) for event in events} == {
        (str(worker), str(i)) for worker in range(4) for i in range(30)
    }
    assert all(event["output"] == "x\n" * 10000 for event in events)


def test_invalid_json_value_does_not_append_partial_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log_event("s", "127.0.0.1", "ls", "ok", "code", 0, [])
    with pytest.raises(ValueError):
        log_event("s", "127.0.0.1", "ls", "bad", "code", float("nan"), [])
    lines, events = read_events(tmp_path)
    assert len(lines) == 1
    assert events[0]["output"] == "ok"


def test_io_failure_is_not_silently_swallowed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "logs").write_text("not a directory", encoding="utf-8")
    with pytest.raises(FileExistsError):
        log_event("s", "127.0.0.1", "ls", "ok", "code", 0, [])


def test_windows_lock_api_uses_one_stable_byte(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import canarynet.logger as logger
    calls = []
    fake = SimpleNamespace(LK_LOCK=1, LK_UNLCK=2,
                           locking=lambda fd, mode, count: calls.append((mode, count)))
    monkeypatch.setattr(logger, "fcntl", None)
    monkeypatch.setattr(logger, "msvcrt", fake, raising=False)
    monkeypatch.chdir(tmp_path)
    log_event("s", "127.0.0.1", "pwd", "ok", "code", 0, [])
    assert calls == [(1, 1), (2, 1)]
    assert read_events(tmp_path)[1][0]["input"] == "pwd"
