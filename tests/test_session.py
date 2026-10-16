import json

import pytest

from canarynet.state.session import Result, Session


@pytest.fixture
def s():
    return Session("t1")


# ---- defaults and seed ---------------------------------------------------
def test_defaults(s):
    assert s.user == "admin" and s.cwd == "/home/admin" and s.src == ""
    assert s.read_file("/etc/hostname").strip() == "web-prod-01"
    assert "22.04" in s.read_file("/etc/os-release")
    assert "admin:x:1000:1000" in s.read_file("/etc/passwd")
    for p in ["/var/log/auth.log", "/var/www/html/index.html", "~/notes.txt"]:
        assert s.read_file(p)


def test_sessions_do_not_share_fs():
    a, b = Session("a"), Session("b")
    a.write_file("/tmp/x", "1")
    assert b.read_file("/tmp/x") is None


def test_result_lists_not_shared():
    r1, r2 = Result("a"), Result("b")
    r1.state_changes.append({"op": "chdir", "path": "/"})
    assert r2.state_changes == [] and r2.exit_code == 0


# ---- resolve ---------------------------------------------------------------
@pytest.mark.parametrize("given,expected", [
    ("notes.txt", "/home/admin/notes.txt"),
    (".", "/home/admin"),
    ("..", "/home"),
    ("../../..", "/"),
    ("/../../etc", "/etc"),
    ("~", "/home/admin"),
    ("~/projects/../x", "/home/admin/x"),
    ("/var/./log/", "/var/log"),
    ("//etc//passwd", "/etc/passwd"),
    ("", "/home/admin"),
])
def test_resolve(s, given, expected):
    assert s.resolve(given) == expected


# ---- mkdir / delete --------------------------------------------------------
def test_mkdir_edges(s):
    assert s.mkdir("new") is True and s.is_dir("/home/admin/new")
    assert s.mkdir("new") is False                 # exists
    assert s.mkdir("/nope/child") is False         # missing parent
    assert s.mkdir("notes.txt/child") is False     # parent is a file
    assert s.mkdir("notes.txt") is False           # file already there


def test_delete_edges(s):
    s.mkdir("d"); s.mkdir("d/e"); s.write_file("d/e/f", "x")
    assert s.delete("d") is True
    assert not any(k.startswith("/home/admin/d") for k in s.fs)
    assert s.delete("d") is False                  # already gone
    assert s.delete("/") is False and "/" in s.fs  # root protected
    assert s.delete("notes.txt") is True and s.read_file("notes.txt") is None
    assert s.is_dir("/home/admin")                 # sibling-prefix safety


def test_delete_does_not_touch_prefix_sibling(s):
    s.mkdir("/tmp/a"); s.mkdir("/tmp/ab")
    s.delete("/tmp/a")
    assert s.is_dir("/tmp/ab")


# ---- chdir -----------------------------------------------------------------
def test_chdir(s):
    assert s.chdir("/var/log") is True and s.cwd == "/var/log"
    assert s.env["PWD"] == "/var/log" and s.env["OLDPWD"] == "/home/admin"
    assert s.chdir("..") is True and s.cwd == "/var"
    assert s.chdir("/etc/passwd") is False and s.cwd == "/var"   # file
    assert s.chdir("/missing") is False and s.cwd == "/var"      # missing
    assert s.chdir("~") is True and s.cwd == "/home/admin"


# ---- read / write / listdir -----------------------------------------------
def test_read_write(s):
    assert s.write_file("a.txt", "hi") is True and s.read_file("~/a.txt") == "hi"
    assert s.write_file("a.txt", "bye") is True and s.read_file("a.txt") == "bye"
    assert s.write_file("/nope/a.txt", "x") is False
    assert s.write_file("/tmp", "x") is False and s.is_dir("/tmp")
    assert s.read_file("/tmp") is None
    assert s.read_file("/missing") is None


def test_listdir(s):
    names = s.listdir("~")
    assert names == sorted(names)
    assert {"notes.txt", "backup.sh", ".bashrc", "projects"} <= set(names)
    assert s.listdir("/missing") is None
    assert s.listdir("/etc/passwd") is None
    assert "passwd" in s.listdir("/etc") and "/" not in s.listdir("/")


# ---- snapshot --------------------------------------------------------------
def test_snapshot_small_even_for_big_session(s):
    for i in range(300):
        s.write_file(f"file_{i:03d}_" + "x" * 100, "data")
    s.history.extend(["cat /etc/passwd " + "A" * 500] * 1000)
    snap = s.snapshot()
    assert snap["cwd"] == "/home/admin" and snap["host"] == "web-prod-01"
    assert len(snap["recent_commands"]) == 5
    assert len(json.dumps(snap)) < 2000
