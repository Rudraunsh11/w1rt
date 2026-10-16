"""Use the real contract when present; otherwise inject a TEST-ONLY stand-in."""

import importlib
import posixpath
import sys
from dataclasses import dataclass, field
from types import ModuleType

import pytest


@dataclass
class StandInResult:
    stdout: str
    exit_code: int = 0
    state_changes: list = field(default_factory=list)


class StandInSession:
    def __init__(self, session_id, user="admin", cwd="/home/admin", env=None,
                 history=None, fs=None, src=""):
        self.session_id, self.user, self.cwd, self.src = session_id, user, cwd, src
        self.env = {} if env is None else env
        self.history = [] if history is None else history
        self.fs = {} if fs is None else fs

    def resolve(self, path):
        if path == "~" or path.startswith("~/"):
            path = self.env.get("HOME", "/home/admin") + path[1:]
        return posixpath.normpath(posixpath.join(self.cwd, path))

    def read_file(self, path):
        node = self.fs.get(self.resolve(path))
        return node["content"] if node and node["type"] == "file" else None

    def write_file(self, path, content):
        path = self.resolve(path)
        if self.listdir(posixpath.dirname(path)) is None or self.listdir(path) is not None:
            raise ValueError("invalid file target")
        self.fs[path] = {"type": "file", "content": content}

    def delete(self, path):
        path = self.resolve(path)
        if path not in self.fs or self.fs[path]["type"] == "dir":
            return False
        del self.fs[path]
        return True

    def mkdir(self, path):
        path = self.resolve(path)
        if path in self.fs or self.listdir(posixpath.dirname(path)) is None:
            return False
        self.fs[path] = {"type": "dir", "content": ""}
        return True

    def listdir(self, path):
        path = self.resolve(path)
        if self.fs.get(path, {}).get("type") != "dir":
            return None
        return sorted(posixpath.basename(key) for key in self.fs
                      if key != path and posixpath.dirname(key) == path)

    def chdir(self, path):
        path = self.resolve(path)
        if self.listdir(path) is None:
            return False
        self.cwd = path
        return True

    def snapshot(self):
        return {"cwd": self.cwd, "user": self.user, "fs": self.fs.copy()}


try:
    session_module = importlib.import_module("canarynet.state.session")
except ModuleNotFoundError as exc:
    if exc.name not in {"canarynet.state", "canarynet.state.session"}:
        raise
    session_module = ModuleType("canarynet.state.session")
    session_module.Session = StandInSession
    session_module.Result = StandInResult
    session_module.TEST_STAND_IN = True
    sys.modules["canarynet.state.session"] = session_module


@pytest.fixture
def session():
    directories = ["/", "/home", "/home/admin", "/etc", "/tmp"]
    fs = {path: {"type": "dir", "content": ""} for path in directories}
    fs.update({
        "/etc/passwd": {"type": "file", "content": "admin:x:1000:1000:Admin:/home/admin:/bin/bash\n"},
        "/home/admin/note.txt": {"type": "file", "content": "hello\n"},
        "/home/admin/.env": {"type": "file", "content": "FAKE_PASSWORD=synthetic-only\n"},
        "/home/admin/empty": {"type": "file", "content": ""},
    })
    return session_module.Session(
        session_id="test-session", user="admin", cwd="/home/admin",
        env={"HOME": "/home/admin", "HOSTNAME": "web-prod-01"}, history=[], fs=fs, src="127.0.0.1",
    )
