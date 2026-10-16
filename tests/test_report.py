import json
import runpy
import sys
from html.parser import HTMLParser

import pytest

from canarynet.report import generate_report, read_events


def event(**changes):
    value = dict(session_id="s1", timestamp="2026-10-16T06:00:00Z", src="127.0.0.1",
                 input="uname", output="Linux", answered_by="code", latency_ms=2.5, tags=["T1082"])
    value.update(changes)
    return value


def write_log(path, events):
    path.write_text(''.join(json.dumps(item) + '\n' for item in events), encoding="utf-8")


def test_groups_and_sorts_with_correct_counts_and_names(tmp_path):
    log, output = tmp_path / "events.jsonl", tmp_path / "report.html"
    write_log(log, [event(input="later", timestamp="2026-10-16T06:02:00Z"),
                    event(input="earlier"), event(session_id="s2", answered_by="model")])
    counts = generate_report(log, output)
    text = output.read_text()
    assert counts == {"events": 3, "sessions": 2, "skipped": 0}
    assert text.index("earlier") < text.index("later")
    assert "Session s1" in text and "Session s2" in text
    assert "System Information Discovery" in text
    assert "2.5 ms" in text and "model" in text
    assert "v20.0" in text and "attempts" in text


def test_every_visitor_field_is_escaped_and_report_is_self_contained(tmp_path):
    payload = '<script>alert("x")</script><img src="http://127.0.0.1:11434/x">&'
    log, output = tmp_path / "log", tmp_path / "report.html"
    write_log(log, [event(session_id=payload, src=payload, input=payload,
                          output=payload, answered_by=payload, tags=[payload])])
    generate_report(log, output)
    text = output.read_text()
    assert payload not in text
    assert "&lt;script&gt;" in text
    class Inspect(HTMLParser):
        def handle_starttag(self, tag, attrs):
            assert tag not in {"script", "img", "iframe", "link"}
            assert not any(key in {"src", "href"} or key.startswith("on") for key, _ in attrs)
    Inspect().feed(text)


def test_malformed_lines_are_counted_including_bad_bytes(tmp_path):
    log, output = tmp_path / "log", tmp_path / "report.html"
    log.write_bytes((json.dumps(event()) + '\nnot json\n[]\n{}\n\n').encode() + b'\xff\n')
    assert generate_report(log, output) == {"events": 1, "sessions": 1, "skipped": 5}
    assert "Malformed lines skipped" in output.read_text()


@pytest.mark.parametrize("changes", [
    {"timestamp": "not a date"}, {"timestamp": "2026-10-16T06:00:00"},
    {"latency_ms": -1}, {"latency_ms": float("nan")}, {"latency_ms": True},
    {"tags": "T1082"}, {"input": []},
])
def test_invalid_event_schema_is_skipped(tmp_path, changes):
    log = tmp_path / "log"
    write_log(log, [event(**changes)])
    rows, skipped, missing = read_events(log)
    assert rows == [] and skipped == 1 and not missing


def test_missing_log_still_produces_useful_report(tmp_path):
    output = tmp_path / "report.html"
    assert generate_report(tmp_path / "missing", output)["events"] == 0
    assert "No log file found" in output.read_text()


def test_module_cli_uses_contract_paths(tmp_path, monkeypatch, capsys):
    (tmp_path / "logs").mkdir()
    write_log(tmp_path / "logs/events.jsonl", [event()])
    monkeypatch.chdir(tmp_path)
    monkeypatch.delitem(sys.modules, "canarynet.report", raising=False)
    runpy.run_module("canarynet.report", run_name="__main__")
    assert (tmp_path / "report.html").exists()
    assert "1 events" in capsys.readouterr().out
