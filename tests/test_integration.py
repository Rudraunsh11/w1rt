"""S3 integration tests. Parts that need a teammate's module skip until it is merged."""
import asyncio
from importlib.util import find_spec

import pytest

from canarynet.router import router
from canarynet.state.session import Result, Session

TEAM_MODULES = ["canarynet.router.handlers", "canarynet.llm.adapter",
                "canarynet.logger", "canarynet.attack.rules"]


def _missing(name):
    return find_spec(name) is None


def test_standins_listed_exactly_for_missing_modules():
    for name in TEAM_MODULES:
        assert (name in router.STANDINS) == _missing(name), name


@pytest.mark.skipif(_missing("canarynet.router.handlers"), reason="handlers.py not merged yet")
def test_multi_step_consistency_from_code(monkeypatch):
    """State persists across commands with the model switched off."""
    monkeypatch.setattr(router, "ask_model", lambda s, line: None)
    monkeypatch.setattr(router, "log_event", lambda *a: None)
    needed = ["mkdir", "cd", "echo", "cat", "pwd", "ls"]
    assert not [c for c in needed if c not in router.HANDLERS], "handlers missing"

    s = Session("it", src="127.0.0.1")
    run = lambda line: router.run(s, line)  # noqa: E731
    run("mkdir work")
    run("cd work")
    assert run("pwd") == "/home/admin/work\n"
    run("echo canary-42 > note.txt")
    assert run("cat note.txt") == "canary-42\n"
    assert "note.txt" in run("ls")
    run("cd ..")
    assert run("cat work/note.txt") == "canary-42\n"


@pytest.mark.skipif(_missing("canarynet.fronts.ssh"), reason="ssh.py not merged yet")
def test_ssh_exec_roundtrip(monkeypatch):
    """Real asyncssh client -> our SSH front -> router -> handler, on loopback."""
    asyncssh = pytest.importorskip("asyncssh")
    from canarynet.fronts import ssh

    monkeypatch.setattr(router, "HANDLERS", {"pwd": lambda s, argv: Result(s.cwd + "\n")})
    monkeypatch.setattr(router, "ask_model", lambda s, line: None)
    monkeypatch.setattr(router, "log_event", lambda *a: None)

    async def go():
        key = asyncssh.generate_private_key("ssh-ed25519")
        listener = await ssh.create_ssh_server(port=0, host_key=key)
        try:
            async with asyncssh.connect("127.0.0.1", port=listener.get_port(), username="admin",
                                        password="admin", known_hosts=None) as conn:
                ok = await conn.run("pwd")
                missing = await conn.run("frobnicate")
        finally:
            listener.close()
        return ok.stdout, missing.stdout

    ok, missing = asyncio.run(go())
    assert ok == "/home/admin\n"
    assert missing == "bash: frobnicate: command not found\n"


@pytest.mark.skipif(_missing("canarynet.fronts.ssh") or _missing("canarynet.router.handlers"),
                    reason="ssh.py or handlers.py not merged yet")
def test_ssh_session_has_planted_canaries(monkeypatch):
    """Every SSH session gets its own fake .env; reusing its password is detected."""
    asyncssh = pytest.importorskip("asyncssh")
    from canarynet.canary import registry
    from canarynet.fronts import ssh

    monkeypatch.setattr(router, "ask_model", lambda s, line: None)
    monkeypatch.setattr(router, "log_event", lambda *a: None)
    registry._reset()

    async def go():
        key = asyncssh.generate_private_key("ssh-ed25519")
        listener = await ssh.create_ssh_server(port=0, host_key=key)
        try:
            async with asyncssh.connect("127.0.0.1", port=listener.get_port(), username="admin",
                                        password="admin", known_hosts=None) as conn:
                first = await conn.run("cat /var/www/html/.env")    # one session per exec
                second = await conn.run("cat /var/www/html/.env")
                aws = await conn.run("cat ~/.aws/credentials")
        finally:
            listener.close()
        return first.stdout, second.stdout, aws.stdout

    try:
        first, second, aws = asyncio.run(go())
        pw1 = first.split("DB_PASSWORD=")[1].strip()
        pw2 = second.split("DB_PASSWORD=")[1].strip()
        assert pw1 and pw1 != pw2                      # unique per session
        assert "aws_secret_access_key = " in aws
        hit = registry.check("root", pw1, "10.0.0.9")
        assert hit["kind"] == "env_db" and hit["planted_src"] == "127.0.0.1"
    finally:
        registry._reset()


@pytest.mark.skipif(_missing("canarynet.fronts.ssh"), reason="ssh.py not merged yet")
def test_ssh_refuses_non_loopback():
    from canarynet.fronts import ssh

    with pytest.raises(ValueError):
        asyncio.run(ssh.create_ssh_server(host="10.0.0.1"))
