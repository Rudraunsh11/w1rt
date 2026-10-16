"""Session and Result classes (Contract-compliant stand-in for Snehank's module)."""

from typing import Any, Dict, List, Optional


class Result:
    def __init__(
        self,
        stdout: str = "",
        exit_code: int = 0,
        state_changes: Optional[List[Dict[str, Any]]] = None,
    ):
        self.stdout = stdout
        self.exit_code = exit_code
        self.state_changes = state_changes if state_changes is not None else []

    def __repr__(self) -> str:
        return f"Result(stdout={self.stdout!r}, exit_code={self.exit_code}, state_changes={self.state_changes})"


class Session:
    def __init__(
        self,
        session_id: str,
        user: str = "admin",
        cwd: str = "/home/admin",
        env: Optional[Dict[str, str]] = None,
        history: Optional[List[str]] = None,
        fs: Optional[Dict[str, Dict[str, str]]] = None,
        src: str = "",
    ):
        self.session_id = session_id
        self.user = user
        self.cwd = cwd
        self.env = env if env is not None else {"USER": user, "HOME": f"/home/{user}", "PWD": cwd}
        self.history = history if history is not None else []
        self.src = src

        # Virtual filesystem: maps absolute path to {"type": "file"|"dir", "content": str}
        if fs is not None:
            self.fs = fs
        else:
            self.fs = {
                "/": {"type": "dir", "content": ""},
                "/home": {"type": "dir", "content": ""},
                f"/home/{user}": {"type": "dir", "content": ""},
            }

    def resolve(self, path: str) -> str:
        """Resolves relative or absolute path against current cwd."""
        if not path:
            return self.cwd
        if path.startswith("/"):
            raw = path
        else:
            raw = f"{self.cwd.rstrip('/')}/{path}"
        # Normalize simple /./ and /../
        parts = []
        for p in raw.split("/"):
            if not p or p == ".":
                continue
            if p == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(p)
        return "/" + "/".join(parts)

    def read_file(self, path: str) -> Optional[str]:
        target = self.resolve(path)
        item = self.fs.get(target)
        if item and item.get("type") == "file":
            return item.get("content", "")
        return None

    def write_file(self, path: str, content: str) -> bool:
        target = self.resolve(path)
        self.fs[target] = {"type": "file", "content": content}
        return True

    def delete(self, path: str) -> bool:
        target = self.resolve(path)
        if target in self.fs:
            del self.fs[target]
            return True
        return False

    def mkdir(self, path: str) -> bool:
        target = self.resolve(path)
        self.fs[target] = {"type": "dir", "content": ""}
        return True

    def listdir(self, path: str) -> Optional[List[str]]:
        target = self.resolve(path).rstrip("/")
        if target != "" and target not in self.fs:
            return None
        entries = set()
        prefix = target + "/" if target else "/"
        for p in self.fs.keys():
            if p == target or not p.startswith(prefix):
                continue
            sub = p[len(prefix):].split("/")[0]
            if sub:
                entries.add(sub)
        return sorted(list(entries))

    def chdir(self, path: str) -> bool:
        target = self.resolve(path)
        item = self.fs.get(target)
        if item and item.get("type") == "dir":
            self.cwd = target
            self.env["PWD"] = target
            return True
        return False

    def snapshot(self) -> Dict[str, Any]:
        """Returns short snapshot for context passing."""
        return {
            "session_id": self.session_id,
            "user": self.user,
            "cwd": self.cwd,
            "env": dict(self.env),
            "files": list(self.fs.keys()),
            "last_commands": self.history[-5:] if self.history else [],
        }
