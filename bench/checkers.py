"""Six automatic multi-step consistency checkers for CanaryNet Lite.

Uses an independent cwd-aware POSIX expected-state oracle.
Preserves exact file whitespace and newlines, requires exact UTF-8 byte matching
for ls size vs cat length with zero tolerance, and reports observations,
contradictions, and PASS/FAIL/N/A status per checker.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple


class TraceStep(NamedTuple):
    cmd: str
    stdout: str
    exit_code: int
    answered_by: str
    state_changed: bool


@dataclass
class CheckerResult:
    name: str
    observations: int
    contradictions: int
    status: str  # "PASS", "FAIL", or "N/A"


class POSIXExpectedStateOracle:
    """Independent cwd-aware POSIX expected-state oracle.

    Tracks filesystem and working directory changes solely from successful mutations.
    """

    def __init__(self, user: str = "admin", initial_cwd: str = "/home/admin"):
        self.user = user
        self.host = "web-prod-01"
        self.cwd = initial_cwd
        self.dirs: Set[str] = {
            "/",
            "/bin",
            "/etc",
            "/home",
            "/home/admin",
            "/opt",
            "/root",
            "/srv",
            "/tmp",
            "/usr",
            "/usr/bin",
            "/var",
            "/var/backups",
            "/var/log",
            "/var/www",
            "/var/www/html",
        }
        self.files: Dict[str, str] = {
            "/etc/hostname": "web-prod-01\n",
            "/etc/passwd": (
                "root:x:0:0:root:/root:/bin/bash\n"
                "daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n"
                "bin:x:2:2:bin:/bin:/usr/sbin/nologin\n"
                "sys:x:3:3:sys:/dev:/usr/sbin/nologin\n"
                "sync:x:4:65534:sync:/bin:/bin/sync\n"
                "www-data:x:33:33:www-data:/var/www:/usr/sbin/nologin\n"
                "backup:x:34:34:backup:/var/backups:/usr/sbin/nologin\n"
                "nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n"
                "systemd-network:x:100:102:systemd Network Management,,,:/run/systemd:/usr/sbin/nologin\n"
                "syslog:x:104:110::/home/syslog:/usr/sbin/nologin\n"
                "sshd:x:110:65534::/run/sshd:/usr/sbin/nologin\n"
                "admin:x:1000:1000:Admin,,,:/home/admin:/bin/bash\n"
            ),
            "/etc/group": (
                "root:x:0:\n"
                "sudo:x:27:admin\n"
                "www-data:x:33:\n"
                "admin:x:1000:\n"
            ),
            "/etc/os-release": (
                'PRETTY_NAME="Ubuntu 22.04.1 LTS"\n'
                'NAME="Ubuntu"\n'
                'VERSION_ID="22.04"\n'
                'VERSION="22.04.1 LTS (Jammy Jellyfish)"\n'
                'VERSION_CODENAME=jammy\n'
                'ID=ubuntu\n'
                'ID_LIKE=debian\n'
                'UBUNTU_CODENAME=jammy\n'
            ),
            f"/home/{self.user}/.bashrc": (
                "# ~/.bashrc: executed by bash(1) for non-login shells.\n"
                "case $- in *i*) ;; *) return;; esac\n"
                "HISTCONTROL=ignoreboth\n"
                "alias ll='ls -alF'\n"
                "alias la='ls -A'\n"
                "PS1='\\u@\\h:\\w\\$ '\n"
            ),
            f"/home/{self.user}/notes.txt": (
                "- rotate db password before friday\n"
                "- move nightly backups off this box\n"
                "- nginx reload needed after cert renewal\n"
            ),
            f"/home/{self.user}/backup.sh": (
                "#!/bin/bash\n"
                "# nightly site backup\n"
                "tar czf /var/backups/www-$(date +%F).tar.gz /var/www/html\n"
            ),
        }
        self.deleted_paths: Set[str] = set()

    def resolve(self, path: str) -> str:
        """Resolves relative, home (~), or parent (..) path into normalized POSIX path."""
        if not path:
            return self.cwd
        if path == "~" or path.startswith("~/"):
            path = f"/home/{self.user}" + path[1:]
        if not path.startswith("/"):
            path = posixpath.join(self.cwd, path)
        norm = posixpath.normpath(path)
        return "/" + norm.lstrip("/")

    def apply_step(self, cmd: str, exit_code: int) -> None:
        """Applies successful mutations to oracle state."""
        cmd_clean = cmd.strip()

        # Handle redirection writes (e.g. echo "..." > file or echo "..." >> file)
        if ">>" in cmd_clean:
            parts = cmd_clean.split(">>", 1)
            target = self.resolve(parts[1].strip())
            match = re.search(r"echo\s+['\"](.*?)['\"]", parts[0])
            content = (match.group(1) if match else "") + "\n"
            existing = self.files.get(target, "")
            self.files[target] = existing + content
            self.deleted_paths.discard(target)
            return
        elif ">" in cmd_clean:
            parts = cmd_clean.split(">", 1)
            target = self.resolve(parts[1].strip())
            match = re.search(r"echo\s+['\"](.*?)['\"]", parts[0])
            content = (match.group(1) if match else "") + "\n"
            self.files[target] = content
            self.deleted_paths.discard(target)
            return

        tokens = cmd_clean.split()
        if not tokens or exit_code != 0:
            return

        op = tokens[0]
        args = tokens[1:]

        if op == "cd":
            target = args[0] if args else f"/home/{self.user}"
            resolved = self.resolve(target)
            # Oracle updates cwd if resolved is known or being created
            self.cwd = resolved
        elif op == "mkdir" and args:
            resolved = self.resolve(args[0])
            self.dirs.add(resolved)
        elif op == "rm" and args:
            target = args[-1]
            resolved = self.resolve(target)
            if resolved in self.files:
                del self.files[resolved]
                self.deleted_paths.add(resolved)
            # Remove any prefix for directory deletion
            prefix = resolved.rstrip("/") + "/"
            to_del = [p for p in self.files if p.startswith(prefix)]
            for p in to_del:
                del self.files[p]
                self.deleted_paths.add(p)


def check_created_file_reads_back_identical(trace: List[TraceStep]) -> CheckerResult:
    """Check 1: A created file reads back identical with exact whitespace/newlines."""
    name = "created_file_reads_back_identical"
    oracle = POSIXExpectedStateOracle()
    observations = 0
    contradictions = 0

    for step in trace:
        cmd = step.cmd.strip()
        cat_match = re.match(r"cat\s+(\S+)", cmd)
        if cat_match and ">" not in cmd:
            target = oracle.resolve(cat_match.group(1))
            if target in oracle.files and target not in oracle.deleted_paths:
                observations += 1
                expected = oracle.files[target]
                actual = step.stdout
                if actual != expected:
                    contradictions += 1

        oracle.apply_step(cmd, step.exit_code)

    status = "N/A" if observations == 0 else ("PASS" if contradictions == 0 else "FAIL")
    return CheckerResult(name, observations, contradictions, status)


def check_deleted_file_absent_from_ls(trace: List[TraceStep]) -> CheckerResult:
    """Check 2: A deleted file is absent from ls (plain, long, and directory listing)."""
    name = "deleted_file_absent_from_ls"
    oracle = POSIXExpectedStateOracle()
    observations = 0
    contradictions = 0

    for step in trace:
        cmd = step.cmd.strip()

        # Check ls queries
        ls_match = re.match(r"ls(?:\s+-\S+)?(?:\s+(\S+))?", cmd)
        if ls_match:
            target_arg = ls_match.group(1)
            target_path = oracle.resolve(target_arg) if target_arg else oracle.cwd
            target_base = posixpath.basename(target_path)

            # Check if this ls target is a deleted file
            if target_path in oracle.deleted_paths:
                observations += 1
                # If deleted, ls should report missing (cannot access / No such file) or exit non-zero
                if step.exit_code == 0 and ("cannot access" not in step.stdout and "No such file" not in step.stdout):
                    contradictions += 1

            # Check if ls directory output includes a deleted file
            for deleted in oracle.deleted_paths:
                if posixpath.dirname(deleted) == target_path:
                    observations += 1
                    del_base = posixpath.basename(deleted)
                    tokens = step.stdout.split()
                    if del_base in tokens:
                        contradictions += 1

        oracle.apply_step(cmd, step.exit_code)

    status = "N/A" if observations == 0 else ("PASS" if contradictions == 0 else "FAIL")
    return CheckerResult(name, observations, contradictions, status)


def check_cd_then_pwd_agree(trace: List[TraceStep]) -> CheckerResult:
    """Check 3: cd then pwd agree, resolving relative, home, and parent (..) paths."""
    name = "cd_then_pwd_agree"
    oracle = POSIXExpectedStateOracle()
    observations = 0
    contradictions = 0

    for step in trace:
        cmd = step.cmd.strip()
        if cmd == "pwd":
            observations += 1
            actual_pwd = step.stdout.strip()
            if actual_pwd != oracle.cwd:
                contradictions += 1

        oracle.apply_step(cmd, step.exit_code)

    status = "N/A" if observations == 0 else ("PASS" if contradictions == 0 else "FAIL")
    return CheckerResult(name, observations, contradictions, status)


def check_ls_size_matches_cat_length(trace: List[TraceStep]) -> CheckerResult:
    """Check 4: ls -l size matches exact UTF-8 byte count of file content with zero tolerance."""
    name = "ls_size_matches_cat_length"
    oracle = POSIXExpectedStateOracle()
    observations = 0
    contradictions = 0

    for step in trace:
        cmd = step.cmd.strip()
        lsl_match = re.match(r"ls\s+-\S*l\S*\s+(\S+)", cmd)
        if lsl_match:
            path = oracle.resolve(lsl_match.group(1))
            if path in oracle.files and path not in oracle.deleted_paths:
                observations += 1
                expected_bytes = len(oracle.files[path].encode("utf-8"))

                # In standard Linux 'ls -l':
                # -rw-r--r-- 1 admin admin <size> Oct 16 11:00 filename
                tokens = step.stdout.split()
                size_found = None
                if len(tokens) >= 5 and tokens[4].isdigit():
                    size_found = int(tokens[4])
                else:
                    for i in range(1, len(tokens) - 1):
                        if tokens[i].isdigit() and any(
                            m in tokens[i + 1]
                            for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                        ):
                            size_found = int(tokens[i])
                            break

                # ZERO tolerance: exact byte count match
                if size_found is None or size_found != expected_bytes:
                    contradictions += 1

        oracle.apply_step(cmd, step.exit_code)

    status = "N/A" if observations == 0 else ("PASS" if contradictions == 0 else "FAIL")
    return CheckerResult(name, observations, contradictions, status)


def check_whoami_and_hostname_never_change(trace: List[TraceStep]) -> CheckerResult:
    """Check 5: whoami and hostname never change during the session."""
    name = "whoami_and_hostname_never_change"
    observations = 0
    contradictions = 0
    seen_users = set()
    seen_hosts = set()

    for step in trace:
        cmd = step.cmd.strip()
        if cmd == "whoami":
            observations += 1
            user = step.stdout.strip()
            seen_users.add(user)
            if user != "admin" or len(seen_users) > 1:
                contradictions += 1
        elif cmd == "hostname":
            observations += 1
            host = step.stdout.strip()
            seen_hosts.add(host)
            if host != "web-prod-01" or len(seen_hosts) > 1:
                contradictions += 1

    status = "N/A" if observations == 0 else ("PASS" if contradictions == 0 else "FAIL")
    return CheckerResult(name, observations, contradictions, status)


def check_repeated_command_same_answer_unless_state_changed(
    trace: List[TraceStep],
) -> CheckerResult:
    """Check 6: A repeated command gives the same answer unless state changed."""
    name = "repeated_command_same_answer"
    observations = 0
    contradictions = 0
    last_cmd_stdout: Dict[str, str] = {}

    for step in trace:
        cmd = step.cmd.strip()

        # State changes invalidate cached outputs
        if step.state_changed:
            last_cmd_stdout.clear()
            continue

        # Skip inherently non-deterministic outputs like uptime
        if cmd in {"uptime", "date"}:
            continue

        if cmd in last_cmd_stdout:
            observations += 1
            if step.stdout != last_cmd_stdout[cmd]:
                contradictions += 1
        else:
            last_cmd_stdout[cmd] = step.stdout

    status = "N/A" if observations == 0 else ("PASS" if contradictions == 0 else "FAIL")
    return CheckerResult(name, observations, contradictions, status)


def evaluate_trace(trace: List[TraceStep]) -> Dict[str, Any]:
    """Runs all 6 consistency checkers over a session execution trace.

    Returns:
        Structured evaluation metrics including observations, contradictions,
        per-checker status, and aggregate pass rate.
    """
    checkers = [
        check_created_file_reads_back_identical(trace),
        check_deleted_file_absent_from_ls(trace),
        check_cd_then_pwd_agree(trace),
        check_ls_size_matches_cat_length(trace),
        check_whoami_and_hostname_never_change(trace),
        check_repeated_command_same_answer_unless_state_changed(trace),
    ]

    total_observations = sum(c.observations for c in checkers)
    total_contradictions = sum(c.contradictions for c in checkers)
    applicable = [c for c in checkers if c.observations > 0]

    # Explicit defect fix: Empty or irrelevant traces NEVER score 100%
    if not applicable or total_observations == 0:
        pass_rate_pct = 0.0
        overall_status = "N/A"
    else:
        passed_count = sum(1 for c in applicable if c.status == "PASS")
        pass_rate_pct = round((passed_count / len(applicable)) * 100.0, 1)
        overall_status = "PASS" if pass_rate_pct == 100.0 else "FAIL"

    return {
        "checkers": checkers,
        "total_observations": total_observations,
        "total_contradictions": total_contradictions,
        "applicable_checkers_count": len(applicable),
        "passed_checkers_count": sum(1 for c in applicable if c.status == "PASS"),
        "pass_rate_pct": pass_rate_pct,
        "status": overall_status,
    }
