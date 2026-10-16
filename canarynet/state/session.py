"""Per-visitor session state: fake filesystem, cwd, env and history. Pure Python, no I/O.

Paths are always POSIX (posixpath, never os.path) so behaviour is identical on Windows.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass, field

HOSTNAME = "web-prod-01"
OS_PRETTY = "Ubuntu 22.04.1 LTS"  # must match the SSH banner
KERNEL = "5.15.0-58-generic"     # must match the SSH banner and uname

_PASSWD = """root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
bin:x:2:2:bin:/bin:/usr/sbin/nologin
sys:x:3:3:sys:/dev:/usr/sbin/nologin
sync:x:4:65534:sync:/bin:/bin/sync
www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin
backup:x:34:34:backup:/var/backups:/usr/sbin/nologin
nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin
systemd-network:x:100:102:systemd Network Management,,,:/run/systemd:/usr/sbin/nologin
syslog:x:104:110::/home/syslog:/usr/sbin/nologin
sshd:x:110:65534::/run/sshd:/usr/sbin/nologin
admin:x:1000:1000:Admin,,,:/home/admin:/bin/bash
"""

_GROUP = """root:x:0:
sudo:x:27:admin
www-data:x:33:
admin:x:1000:
"""

_OS_RELEASE = """PRETTY_NAME="Ubuntu 22.04.1 LTS"
NAME="Ubuntu"
VERSION_ID="22.04"
VERSION="22.04.1 LTS (Jammy Jellyfish)"
VERSION_CODENAME=jammy
ID=ubuntu
ID_LIKE=debian
UBUNTU_CODENAME=jammy
"""

_AUTH_LOG = """Oct 16 08:02:11 web-prod-01 sshd[1021]: Server listening on :: port 22.
Oct 16 08:15:42 web-prod-01 sshd[1188]: Accepted publickey for admin from 10.0.2.15 port 51544 ssh2
Oct 16 08:15:42 web-prod-01 sshd[1188]: pam_unix(sshd:session): session opened for user admin(uid=1000) by (uid=0)
Oct 16 08:31:07 web-prod-01 sudo:    admin : TTY=pts/0 ; PWD=/home/admin ; USER=root ; COMMAND=/usr/bin/systemctl restart nginx
Oct 16 09:02:55 web-prod-01 sshd[1240]: Invalid user test from 10.0.2.44 port 40212
"""

_INDEX_HTML = """<!DOCTYPE html>
<html><head><title>web-prod-01</title></head>
<body><h1>It works</h1><p>Internal status page.</p></body></html>
"""

_BASHRC = """# ~/.bashrc: executed by bash(1) for non-login shells.
case $- in *i*) ;; *) return;; esac
HISTCONTROL=ignoreboth
alias ll='ls -alF'
alias la='ls -A'
PS1='\\u@\\h:\\w\\$ '
"""

_NOTES = """- rotate db password before friday
- move nightly backups off this box
- nginx reload needed after cert renewal
"""

_BACKUP_SH = """#!/bin/bash
# nightly site backup
tar czf /var/backups/www-$(date +%F).tar.gz /var/www/html
"""


def _seed_fs(home: str) -> dict:
    """Build a fresh fake filesystem (new dict per session, never shared)."""
    dirs = ["/", "/bin", "/etc", "/home", "/opt", "/root", "/srv", "/tmp", "/usr",
            "/usr/bin", "/var", "/var/backups", "/var/log", "/var/www", "/var/www/html",
            home, home + "/projects"]
    files = {
        "/etc/passwd": _PASSWD,
        "/etc/group": _GROUP,
        "/etc/hostname": HOSTNAME + "\n",
        "/etc/os-release": _OS_RELEASE,
        "/var/log/auth.log": _AUTH_LOG,
        "/var/www/html/index.html": _INDEX_HTML,
        home + "/.bashrc": _BASHRC,
        home + "/.profile": "# ~/.profile\n[ -f ~/.bashrc ] && . ~/.bashrc\n",
        home + "/notes.txt": _NOTES,
        home + "/backup.sh": _BACKUP_SH,
    }
    fs = {d: {"type": "dir", "content": ""} for d in dirs}
    fs.update({p: {"type": "file", "content": c} for p, c in files.items()})
    return fs


@dataclass
class Result:
    """What a handler or the model returns for one command."""
    stdout: str
    exit_code: int = 0
    state_changes: list = field(default_factory=list)


@dataclass
class Session:
    session_id: str
    user: str = "admin"
    cwd: str = "/home/admin"
    env: dict | None = None
    history: list | None = None
    fs: dict | None = None
    src: str = ""

    def __post_init__(self):
        if self.fs is None:
            self.fs = _seed_fs(self.home)
        self.fs.setdefault("/", {"type": "dir", "content": ""})
        if self.history is None:
            self.history = []
        if self.env is None:
            self.env = {
                "USER": self.user, "LOGNAME": self.user, "HOME": self.home,
                "SHELL": "/bin/bash", "PWD": self.cwd, "HOSTNAME": HOSTNAME,
                "LANG": "C.UTF-8",
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            }

    # ---- helpers -------------------------------------------------------
    @property
    def home(self) -> str:
        return "/root" if self.user == "root" else f"/home/{self.user}"

    def is_dir(self, path: str) -> bool:
        node = self.fs.get(self.resolve(path))
        return bool(node) and node["type"] == "dir"

    def is_file(self, path: str) -> bool:
        node = self.fs.get(self.resolve(path))
        return bool(node) and node["type"] == "file"

    # ---- contract ------------------------------------------------------
    def resolve(self, path: str) -> str:
        """Absolute, normalised path. Handles relative, ., .., ~ and ~/x."""
        if not path:
            return self.cwd
        if path == "~" or path.startswith("~/"):
            path = self.home + path[1:]
        if not path.startswith("/"):
            path = posixpath.join(self.cwd, path)
        norm = posixpath.normpath(path)
        # POSIX normpath keeps a leading "//"; collapse it.
        return "/" + norm.lstrip("/")

    def read_file(self, path: str) -> str | None:
        node = self.fs.get(self.resolve(path))
        if node and node["type"] == "file":
            return node["content"]
        return None

    def write_file(self, path: str, content: str) -> bool:
        """Create or overwrite a file. False if parent dir is missing or path is a dir."""
        p = self.resolve(path)
        if self.fs.get(p, {}).get("type") == "dir":
            return False
        if self.fs.get(posixpath.dirname(p), {}).get("type") != "dir":
            return False
        self.fs[p] = {"type": "file", "content": content}
        return True

    def delete(self, path: str) -> bool:
        """Remove a file, or a dir with everything under it. Never removes "/"."""
        p = self.resolve(path)
        if p == "/" or p not in self.fs:
            return False
        prefix = p + "/"
        for key in [k for k in self.fs if k == p or k.startswith(prefix)]:
            del self.fs[key]
        return True

    def mkdir(self, path: str) -> bool:
        """Create one dir. False if it exists or the parent is not a dir (no -p)."""
        p = self.resolve(path)
        if p in self.fs:
            return False
        if self.fs.get(posixpath.dirname(p), {}).get("type") != "dir":
            return False
        self.fs[p] = {"type": "dir", "content": ""}
        return True

    def listdir(self, path: str) -> list | None:
        p = self.resolve(path)
        if self.fs.get(p, {}).get("type") != "dir":
            return None
        return sorted(posixpath.basename(k) for k in self.fs
                      if k != p and posixpath.dirname(k) == p)

    def chdir(self, path: str) -> bool:
        p = self.resolve(path)
        if self.fs.get(p, {}).get("type") != "dir":
            return False
        self.env["OLDPWD"] = self.cwd
        self.cwd = p
        self.env["PWD"] = p
        return True

    def snapshot(self) -> dict:
        """Small summary for the model prompt. Size is capped regardless of session size."""
        listing = self.listdir(self.cwd) or []
        return {
            "user": self.user,
            "host": HOSTNAME,
            "os": OS_PRETTY,
            "cwd": self.cwd,
            "home": self.home,
            "cwd_listing": [name[:40] for name in listing[:20]],
            "recent_commands": [line[:80] for line in self.history[-5:]],
        }
