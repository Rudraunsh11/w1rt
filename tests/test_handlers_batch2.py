from copy import deepcopy

import pytest

from canarynet.router.handlers import HANDLERS


def call(session, command, *args):
    result = HANDLERS[command](session, list(args))
    assert result.state_changes == []
    return result


def test_echo_prints_only_without_expansion_or_redirection(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = deepcopy(session.fs)
    assert call(session, "echo", "hello", ">", "note").stdout == "hello > note\n"
    assert call(session, "echo", "$(whoami)", "$HOME").stdout == "$(whoami) $HOME\n"
    assert call(session, "echo", "-n", "hello").stdout == "hello"
    assert call(session, "echo").stdout == "\n"
    assert session.fs == before
    assert list(tmp_path.iterdir()) == []


def test_virtual_create_read_delete_sequence(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert call(session, "mkdir", "work").exit_code == 0
    assert call(session, "touch", "work/note").exit_code == 0
    assert session.read_file("work/note") == ""
    session.write_file("work/note", "saved\n")  # Router owns writing redirected stdout.
    assert call(session, "cat", "work/note").stdout == "saved\n"
    assert call(session, "touch", "work/note").exit_code == 0
    assert session.read_file("work/note") == "saved\n"
    assert call(session, "rm", "work/note").exit_code == 0
    assert session.read_file("work/note") is None
    assert list(tmp_path.iterdir()) == []


def test_mkdir_parents_and_existing_directory(session):
    assert call(session, "mkdir", "-p", "nested/child").exit_code == 0
    assert session.listdir("nested/child") == []
    assert call(session, "mkdir", "-p", "nested/child").exit_code == 0
    assert call(session, "mkdir", "nested").exit_code == 1


@pytest.mark.parametrize("command,args", [
    ("mkdir", []), ("mkdir", ["missing/child"]), ("mkdir", ["note.txt/child"]),
    ("touch", []), ("touch", ["missing/child"]), ("touch", ["note.txt/child"]),
    ("rm", []), ("rm", ["missing"]), ("rm", ["/etc"]), ("rm", ["-r", "/etc"]),
])
def test_failure_paths(session, command, args):
    assert call(session, command, *args).exit_code == 1


def test_force_rm_of_missing_file_succeeds(session):
    assert call(session, "rm", "-f", "missing").exit_code == 0


def test_ps_uses_static_persona_not_real_processes(session):
    output = call(session, "ps", "aux").stdout
    assert "sshd" in output
    assert "systemd" in output
    assert "bash" in output
    assert output == call(session, "ps").stdout


def test_history_reads_without_mutating_or_adding_itself(session):
    session.history.extend(["ls", "whoami", "pwd"])
    assert call(session, "history").stdout == "    1  ls\n    2  whoami\n    3  pwd\n"
    assert call(session, "history", "1").stdout == "    3  pwd\n"
    assert call(session, "history", "0").stdout == ""
    assert call(session, "history", "-c").exit_code == 1
    assert session.history == ["ls", "whoami", "pwd"]
