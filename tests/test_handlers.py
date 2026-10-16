import importlib
from copy import deepcopy

import pytest

from canarynet.router.handlers import HANDLERS, command
from canarynet.state.session import KERNEL


@pytest.mark.parametrize("name,argv,expected", [
    ("pwd", [], "/home/admin\n"), ("whoami", [], "admin\n"),
    ("hostname", [], "web-prod-01\n"), ("uname", [], "Linux\n"),
    ("uname", ["-a"], f"Linux web-prod-01 {KERNEL} #101-Ubuntu SMP x86_64 GNU/Linux\n"),
    ("uname", ["-r"], KERNEL + "\n"),
    ("id", [], "uid=1000(admin) gid=1000(admin) groups=1000(admin),27(sudo)\n"),
    ("cat", ["note.txt"], "hello\n"), ("cat", ["empty"], ""),
])
def test_core_commands(session, name, argv, expected):
    before = deepcopy(session.fs)
    result = HANDLERS[name](session, argv)
    assert result.stdout == expected
    assert result.exit_code == 0
    assert result.state_changes == []
    assert session.fs == before


def test_listing_flags_hide_or_show_dotfiles(session):
    assert HANDLERS["ls"](session, []).stdout.splitlines() == ["empty", "note.txt"]
    assert HANDLERS["ls"](session, ["-a"]).stdout.splitlines() == [".", "..", ".env", "empty", "note.txt"]
    detailed = HANDLERS["ls"](session, ["-la"]).stdout
    assert "-rw-r--r--" in detailed
    assert "drwxr-xr-x" in detailed
    assert ".env" in detailed
    assert "note.txt" in detailed


def test_cd_changes_only_session_state_and_resolves_relative_paths(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert HANDLERS["cd"](session, ["/etc"]).exit_code == 0
    assert HANDLERS["pwd"](session, []).stdout == "/etc\n"
    assert HANDLERS["cat"](session, ["./passwd"]).stdout.startswith("admin:x:")
    assert HANDLERS["cd"](session, []).exit_code == 0
    assert session.cwd == "/home/admin"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name,argv,message", [
    ("cat", ["x"], "cat: x: No such file or directory\n"),
    ("cat", ["/etc"], "cat: /etc: Is a directory\n"),
    ("cd", ["note.txt"], "cd: note.txt: Not a directory\n"),
    ("cd", ["/missing"], "cd: /missing: No such file or directory\n"),
])
def test_realistic_errors(session, name, argv, message):
    result = HANDLERS[name](session, argv)
    assert result.exit_code == 1
    assert result.stdout == message
    assert result.state_changes == []


def test_host_identity_is_never_used(session):
    session.user = "visitor"
    session.env["HOSTNAME"] = "another-decoy"
    assert HANDLERS["whoami"](session, []).stdout == "visitor\n"
    assert HANDLERS["hostname"](session, []).stdout == "another-decoy\n"
    assert "another-decoy" in HANDLERS["uname"](session, ["-a"]).stdout
    assert "visitor" in HANDLERS["id"](session, []).stdout


def test_add_handler_with_test_requires_no_router_edit(session, monkeypatch):
    from canarynet.state.session import Result
    @command("test-only-ping")
    def ping(session, argv):
        return Result("pong\n", state_changes=[])
    try:
        assert HANDLERS["test-only-ping"](session, []).stdout == "pong\n"
    finally:
        del HANDLERS["test-only-ping"]


def test_router_dispatch_harness_without_model_calls(session):
    # TEST-ONLY dispatch harness until Snehank's actual router arrives.
    import shlex
    def run(line):
        name, *argv = shlex.split(line)
        return HANDLERS[name](session, argv).stdout
    assert "note.txt" in run("ls")
    assert run("cd /etc") == ""
    assert run("pwd") == "/etc\n"
    assert "admin:x:" in run("cat /etc/passwd")


def test_real_router_integration_when_available(session, monkeypatch, tmp_path):
    try:
        router = importlib.import_module("canarynet.router.router")
    except ModuleNotFoundError as exc:
        if exc.name == "canarynet.router.router":
            pytest.skip("VERIFY: Snehank's router.py has not arrived; harness tested separately")
        raise
    monkeypatch.chdir(tmp_path)
    def no_model(*args, **kwargs):
        pytest.fail("core command unexpectedly called the model")
    monkeypatch.setattr(router, "ask_model", no_model, raising=False)
    assert "note.txt" in router.run(session, "ls")
    assert router.run(session, "cd /etc") == ""
    assert router.run(session, "pwd") == "/etc\n"
    assert "admin:x:" in router.run(session, "cat /etc/passwd")
