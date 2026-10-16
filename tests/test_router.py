"""Router tests with stand-ins for handlers, ask_model, log_event and tag."""
from types import SimpleNamespace

import pytest

from canarynet.router import router
from canarynet.state.session import Result, Session


@pytest.fixture
def t(monkeypatch):
    ctx = SimpleNamespace(events=[], model_calls=[], reply=None, handler_calls=[],
                          s=Session("r1", src="127.0.0.1"))

    def echo(session, argv):
        ctx.handler_calls.append(("echo", argv))
        return Result(" ".join(argv) + "\n")

    def cat(session, argv):
        ctx.handler_calls.append(("cat", argv))
        text = session.read_file(argv[0])
        if text is None:
            return Result(f"cat: {argv[0]}: No such file or directory\n", exit_code=1)
        return Result(text)

    def boom(session, argv):
        raise RuntimeError("handler bug")

    def fake_model(session, line):
        ctx.model_calls.append(line)
        return ctx.reply

    monkeypatch.setattr(router, "HANDLERS", {"echo": echo, "cat": cat, "boom": boom})
    monkeypatch.setattr(router, "ask_model", fake_model)
    monkeypatch.setattr(router, "log_event", lambda *a: ctx.events.append(a))
    monkeypatch.setattr(router, "tag", lambda line: ["T1082"] if "uname" in line else [])
    return ctx


# ---- handlers --------------------------------------------------------------
def test_handler_answers_without_model(t):
    assert router.run(t.s, "echo hello world") == "hello world\n"
    assert t.model_calls == []
    assert t.handler_calls == [("echo", ["hello", "world"])]  # argv excludes the command


def test_handler_crash_falls_back_to_model(t):
    t.reply = Result("ok\n")
    assert router.run(t.s, "boom now") == "ok\n"
    assert t.model_calls == ["boom now"]
    assert t.events[0][4] == "model:handler_error"


# ---- redirection -------------------------------------------------------------
def test_redirect_write_and_append(t):
    assert router.run(t.s, "echo one > out.txt") == ""
    assert t.s.read_file("/home/admin/out.txt") == "one\n"
    assert router.run(t.s, "echo two>>out.txt") == ""          # no spaces
    assert t.s.read_file("out.txt") == "one\ntwo\n"
    router.run(t.s, "echo three > out.txt")                     # > truncates
    assert t.s.read_file("out.txt") == "three\n"


def test_redirect_quoted_gt_is_not_a_redirect(t):
    assert router.run(t.s, "echo 'a > b'") == "a > b\n"


def test_redirect_errors(t):
    assert "syntax error" in router.run(t.s, "echo hi >")
    assert router.run(t.s, "echo hi > /nope/f") == "bash: /nope/f: No such file or directory\n"
    assert router.run(t.s, "echo hi > /tmp") == "bash: /tmp: Is a directory\n"


def test_failed_command_message_stays_on_screen(t):
    out = router.run(t.s, "cat /missing > f.txt")
    assert out == "cat: /missing: No such file or directory\n"
    assert t.s.read_file("f.txt") == ""


def test_stderr_and_devnull_redirects(t):
    assert router.run(t.s, "echo hi 2>/dev/null") == "hi\n"
    assert t.handler_calls[-1] == ("echo", ["hi"])                 # "2" not passed as argv
    assert router.run(t.s, "echo hi > /dev/null") == ""
    assert "/dev/null" not in t.s.fs


def test_model_output_can_be_redirected(t):
    t.reply = Result("Linux web-prod-01\n")
    assert router.run(t.s, "uname -a > u.txt") == ""
    assert t.model_calls == ["uname -a"]                            # redirect stripped
    assert t.s.read_file("u.txt") == "Linux web-prod-01\n"


# ---- unknown commands / model -------------------------------------------------
def test_unknown_command_model_none(t):
    t.reply = None
    assert router.run(t.s, "frobnicate --x") == "bash: frobnicate: command not found\n"
    assert t.model_calls == ["frobnicate --x"]
    assert t.events[0][4] == "not_found"


def test_model_exception_is_not_found(t, monkeypatch):
    def broken(session, line):
        raise ConnectionError("ollama down")
    monkeypatch.setattr(router, "ask_model", broken)
    assert router.run(t.s, "wget x") == "bash: wget: command not found\n"


def test_model_changes_applied_exactly_once(t, monkeypatch):
    writes = []
    real_write = t.s.write_file
    monkeypatch.setattr(t.s, "write_file", lambda p, c: writes.append(p) or real_write(p, c))
    t.reply = Result("done\n", 0, [
        {"op": "create_file", "path": "/tmp/m.txt", "content": "x"},
        {"op": "set_env", "path": "FOO", "content": "bar"},
        {"op": "chdir", "path": "/tmp"},
    ])
    assert router.run(t.s, "installer.sh") == "done\n"
    assert writes == ["/tmp/m.txt"]
    assert t.s.read_file("/tmp/m.txt") == "x"
    assert t.s.env["FOO"] == "bar" and t.s.cwd == "/tmp"
    assert t.events[0][4] == "model"


def test_dict_reply_and_bad_changes_are_skipped(t):
    t.reply = {"stdout": "ok", "exit_code": 0, "state_changes": [
        {"op": "rm_rf", "path": "/"}, {"op": "write_file", "path": 5}, "junk",
        {"op": "set_env", "path": "BAD NAME", "content": "x"},
        {"op": "delete_file", "path": "/home/admin/notes.txt"},
    ]}
    assert router.run(t.s, "weird") == "ok"
    assert t.s.read_file("/home/admin/notes.txt") is None
    assert "/" in t.s.fs and "BAD NAME" not in t.s.env


def test_malformed_reply_is_not_found(t):
    t.reply = {"stdout": 123, "exit_code": 0, "state_changes": []}
    assert router.run(t.s, "x") == "bash: x: command not found\n"


def test_compound_line_goes_to_model_whole(t):
    t.reply = Result("root:x:0:0\n")
    assert router.run(t.s, "cat /etc/passwd | grep root") == "root:x:0:0\n"
    assert t.model_calls == ["cat /etc/passwd | grep root"]
    assert t.handler_calls == []


# ---- history and logging -----------------------------------------------------
def test_history_and_one_log_event_per_command(t):
    t.reply = None
    for line in ["echo a", "uname -a", "nope", "echo b > f"]:
        router.run(t.s, line)
    assert t.s.history == ["echo a", "uname -a", "nope", "echo b > f"]
    assert len(t.events) == 4
    sid, src, inp, out, by, latency, tags = t.events[1]
    assert (sid, src, inp, by, tags) == ("r1", "127.0.0.1", "uname -a", "not_found", ["T1082"])
    assert out == "bash: uname: command not found\n"
    assert isinstance(latency, float) and latency >= 0


def test_empty_line_is_ignored(t):
    assert router.run(t.s, "   ") == ""
    assert t.s.history == [] and t.events == []


def test_unbalanced_quote_is_syntax_error_and_logged(t):
    assert "syntax error" in router.run(t.s, "echo 'oops")
    assert len(t.events) == 1 and t.s.history == ["echo 'oops"]
