"""Production Session/router -> handlers -> real JSONL -> HTML report."""
import json

from canarynet.router import router
from canarynet.state.session import Session
from canarynet.report import generate_report


def test_no_standins_for_rudraunsh_modules():
    assert "canarynet.logger" not in router.STANDINS
    assert "canarynet.router.handlers" not in router.STANDINS
    assert "canarynet.attack.rules" not in router.STANDINS


def test_router_file_bytes_are_exact_including_no_final_newline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(router, "ask_model", lambda *args: None)
    session = Session("byte-check")
    assert router.run(session, "echo -n abc > /tmp/exact") == ""
    assert session.read_file("/tmp/exact") == "abc"
    assert router.run(session, "cat /tmp/exact") == "abc"
    listing = router.run(session, "ls -l /tmp/exact")
    assert int(listing.split()[4]) == len(session.read_file("/tmp/exact").encode("utf-8")) == 3
    assert router.run(session, "echo -n d >> /tmp/exact") == ""
    assert router.run(session, "cat /tmp/exact") == "abcd"


def test_real_log_and_report_follow_the_complete_command_chain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def no_model(*args):
        raise AssertionError("ordinary commands must use handlers")
    monkeypatch.setattr(router, "ask_model", no_model)
    session = Session("integrated", src="127.0.0.1")
    commands = ["ls", "cd /etc", "pwd", "cat /etc/passwd"]
    outputs = [router.run(session, line) for line in commands]
    events = [json.loads(line) for line in (tmp_path / "logs/events.jsonl").read_text().splitlines()]
    assert [event["input"] for event in events] == commands
    assert [event["output"] for event in events] == outputs
    assert all(event["answered_by"] == "code" for event in events)
    assert events[0]["tags"] == ["T1083"]
    assert events[-1]["tags"] == ["T1087.001"]
    assert outputs[2] == "/etc\n"
    assert "admin:x:1000" in outputs[3]
    assert generate_report()["events"] == 4
    assert "System Owner" not in (tmp_path / "report.html").read_text()
    assert "Account Discovery: Local Account" in (tmp_path / "report.html").read_text()
