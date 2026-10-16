"""Six automatic multi-step consistency checkers for CanaryNet Lite."""

import re
from typing import Any, Dict, List, NamedTuple, Tuple


class TraceStep(NamedTuple):
    cmd: str
    stdout: str
    exit_code: int
    answered_by: str
    state_changed: bool


def check_created_file_reads_back_identical(trace: List[TraceStep]) -> Tuple[bool, int]:
    """Check 1: A created file reads back identical.

    Returns:
        (passed: bool, contradictions: int)
    """
    file_contents: Dict[str, str] = {}
    contradictions = 0

    for step in trace:
        cmd = step.cmd.strip()

        # Track file deletions: if deleted, remove from expected active contents
        rm_match = re.match(r"rm\s+(?:-\S+\s+)?(\S+)", cmd)
        if rm_match:
            del_path = rm_match.group(1).strip()
            # Remove any keys matching full path or basename
            keys_to_del = [k for k in file_contents if k == del_path or k.endswith("/" + del_path)]
            for k in keys_to_del:
                del file_contents[k]

        # Detect creation via echo '...' > path or echo "..." > path
        match = re.search(r"echo\s+['\"](.*?)['\"]\s*>\s*(\S+)", cmd)
        if match:
            expected_content = match.group(1).strip()
            path = match.group(2).strip()
            file_contents[path] = expected_content

        # Detect cat <path>
        cat_match = re.match(r"cat\s+(\S+)", cmd)
        if cat_match:
            path = cat_match.group(1).strip()
            # Match either direct path or ending with path
            matched_key = None
            if path in file_contents:
                matched_key = path
            else:
                for k in file_contents:
                    if k.endswith("/" + path):
                        matched_key = k
                        break

            if matched_key:
                actual_content = step.stdout.strip()
                if actual_content != file_contents[matched_key]:
                    contradictions += 1

    passed = (contradictions == 0)
    return passed, contradictions


def check_deleted_file_absent_from_ls(trace: List[TraceStep]) -> Tuple[bool, int]:
    """Check 2: A deleted file is absent from ls."""
    deleted_files = set()
    contradictions = 0

    for step in trace:
        cmd = step.cmd.strip()
        rm_match = re.match(r"rm\s+(?:-\S+\s+)?(\S+)", cmd)
        if rm_match:
            path = rm_match.group(1).strip()
            deleted_files.add(path.split("/")[-1])

        ls_match = re.match(r"ls\s+(?:-\S+\s+)?(\S+)", cmd)
        if ls_match:
            path = ls_match.group(1).strip()
            basename = path.split("/")[-1]
            if basename in deleted_files:
                # If deleted, ls should report not found or exit non-zero
                if step.exit_code == 0 and ("No such file" not in step.stdout and "cannot access" not in step.stdout and step.stdout.strip() == basename):
                    contradictions += 1

    passed = (contradictions == 0)
    return passed, contradictions


def check_cd_then_pwd_agree(trace: List[TraceStep]) -> Tuple[bool, int]:
    """Check 3: cd then pwd agree."""
    last_cd_target = None
    contradictions = 0

    for step in trace:
        cmd = step.cmd.strip()
        cd_match = re.match(r"cd\s+(\S+)", cmd)
        if cd_match:
            last_cd_target = cd_match.group(1).strip()
        elif cmd == "pwd":
            if last_cd_target is not None:
                actual_pwd = step.stdout.strip()
                target_base = last_cd_target.rstrip("/").split("/")[-1]
                if last_cd_target == "..":
                    pass  # Path shortened
                elif last_cd_target.startswith("/"):
                    if actual_pwd != last_cd_target:
                        contradictions += 1
                elif not actual_pwd.endswith(target_base):
                    contradictions += 1
                last_cd_target = None

    passed = (contradictions == 0)
    return passed, contradictions


def check_ls_size_matches_cat_length(trace: List[TraceStep]) -> Tuple[bool, int]:
    """Check 4: ls -l size matches cat length."""
    cat_lengths: Dict[str, int] = {}
    contradictions = 0

    for step in trace:
        cmd = step.cmd.strip()
        cat_match = re.match(r"cat\s+(\S+)", cmd)
        if cat_match:
            path = cat_match.group(1).strip()
            basename = path.split("/")[-1]
            cat_lengths[basename] = len(step.stdout.encode("utf-8"))

        lsl_match = re.match(r"ls\s+-l\s+(\S+)", cmd)
        if lsl_match:
            path = lsl_match.group(1).strip()
            basename = path.split("/")[-1]
            if basename in cat_lengths:
                tokens = step.stdout.split()
                # In standard Linux 'ls -l':
                # -rw-r--r-- 1 admin admin 17 Oct 16 11:00 file.txt
                # Token 0: perms, Token 1: links, Token 2: user, Token 3: group, Token 4: size
                size_found = None
                if len(tokens) >= 5 and tokens[4].isdigit():
                    size_found = int(tokens[4])
                else:
                    # Fallback: scan for any digit right before month (Oct, Nov, etc.)
                    for i in range(1, len(tokens) - 1):
                        if tokens[i].isdigit() and any(m in tokens[i + 1] for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]):
                            size_found = int(tokens[i])
                            break

                if size_found is not None:
                    if abs(size_found - cat_lengths[basename]) > 5:
                        contradictions += 1

    passed = (contradictions == 0)
    return passed, contradictions


def check_whoami_and_hostname_never_change(trace: List[TraceStep]) -> Tuple[bool, int]:
    """Check 5: whoami and hostname never change during the session."""
    seen_users = set()
    seen_hosts = set()
    contradictions = 0

    for step in trace:
        cmd = step.cmd.strip()
        if cmd == "whoami":
            user = step.stdout.strip()
            seen_users.add(user)
            if len(seen_users) > 1:
                contradictions += 1
        elif cmd == "hostname":
            host = step.stdout.strip()
            seen_hosts.add(host)
            if len(seen_hosts) > 1:
                contradictions += 1

    passed = (contradictions == 0)
    return passed, contradictions


def check_repeated_command_same_answer_unless_state_changed(
    trace: List[TraceStep],
) -> Tuple[bool, int]:
    """Check 6: A repeated command gives the same answer unless state changed."""
    last_cmd_res: Dict[str, str] = {}
    contradictions = 0

    for step in trace:
        cmd = step.cmd.strip()
        if step.state_changed:
            last_cmd_res.clear()
            continue

        if cmd in {"uptime", "date"}:
            continue

        if cmd in last_cmd_res:
            if step.stdout.strip() != last_cmd_res[cmd].strip():
                contradictions += 1
        else:
            last_cmd_res[cmd] = step.stdout

    passed = (contradictions == 0)
    return passed, contradictions


def evaluate_trace(trace: List[TraceStep]) -> Dict[str, Any]:
    """Runs all 6 consistency checkers over a session execution trace."""
    c1, n1 = check_created_file_reads_back_identical(trace)
    c2, n2 = check_deleted_file_absent_from_ls(trace)
    c3, n3 = check_cd_then_pwd_agree(trace)
    c4, n4 = check_ls_size_matches_cat_length(trace)
    c5, n5 = check_whoami_and_hostname_never_change(trace)
    c6, n6 = check_repeated_command_same_answer_unless_state_changed(trace)

    checks = [
        ("created_file_reads_back_identical", c1, n1),
        ("deleted_file_absent_from_ls", c2, n2),
        ("cd_then_pwd_agree", c3, n3),
        ("ls_size_matches_cat_length", c4, n4),
        ("whoami_and_hostname_never_change", c5, n5),
        ("repeated_command_same_answer", c6, n6),
    ]

    total_checks = len(checks)
    passed_checks = sum(1 for _, passed, _ in checks if passed)
    total_contradictions = sum(n for _, _, n in checks)

    return {
        "checks": checks,
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "pass_rate": round(passed_checks / total_checks, 2),
        "total_contradictions": total_contradictions,
    }
