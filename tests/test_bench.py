"""Unit tests for the CanaryNet benchmark suite."""

import pytest
from bench.playbooks import PLAYBOOKS
from bench.checkers import (
    TraceStep,
    check_created_file_reads_back_identical,
    check_deleted_file_absent_from_ls,
    check_cd_then_pwd_agree,
    check_ls_size_matches_cat_length,
    check_whoami_and_hostname_never_change,
    check_repeated_command_same_answer_unless_state_changed,
    evaluate_trace,
)
from bench.run import run_benchmark


def test_playbooks_structure():
    """Verify 5 seeded playbooks are defined and contain approximately 10 commands each."""
    assert len(PLAYBOOKS) == 5
    for name, cmds in PLAYBOOKS.items():
        assert isinstance(cmds, list)
        assert len(cmds) == 10, f"Playbook {name} has {len(cmds)} commands, expected 10"


def test_checker_created_file():
    trace_valid = [
        TraceStep("echo 'hello' > /tmp/a.txt", "", 0, "code", True),
        TraceStep("cat /tmp/a.txt", "hello\n", 0, "code", False),
    ]
    passed, contr = check_created_file_reads_back_identical(trace_valid)
    assert passed is True
    assert contr == 0

    trace_invalid = [
        TraceStep("echo 'hello' > /tmp/a.txt", "", 0, "code", True),
        TraceStep("cat /tmp/a.txt", "corrupted\n", 0, "model", False),
    ]
    passed, contr = check_created_file_reads_back_identical(trace_invalid)
    assert passed is False
    assert contr == 1


def test_checker_deleted_file():
    trace_valid = [
        TraceStep("rm /tmp/a.txt", "", 0, "code", True),
        TraceStep("ls /tmp/a.txt", "ls: cannot access '/tmp/a.txt': No such file\n", 2, "code", False),
    ]
    passed, contr = check_deleted_file_absent_from_ls(trace_valid)
    assert passed is True
    assert contr == 0

    trace_invalid = [
        TraceStep("rm /tmp/a.txt", "", 0, "code", True),
        TraceStep("ls /tmp/a.txt", "a.txt\n", 0, "model", False),
    ]
    passed, contr = check_deleted_file_absent_from_ls(trace_invalid)
    assert passed is False
    assert contr == 1


def test_checker_cd_pwd():
    trace_valid = [
        TraceStep("cd /tmp", "", 0, "code", True),
        TraceStep("pwd", "/tmp\n", 0, "code", False),
    ]
    passed, contr = check_cd_then_pwd_agree(trace_valid)
    assert passed is True
    assert contr == 0

    trace_invalid = [
        TraceStep("cd /tmp", "", 0, "code", True),
        TraceStep("pwd", "/home/admin\n", 0, "model", False),
    ]
    passed, contr = check_cd_then_pwd_agree(trace_invalid)
    assert passed is False
    assert contr == 1


def test_checker_whoami_hostname_invariable():
    trace_valid = [
        TraceStep("whoami", "admin\n", 0, "code", False),
        TraceStep("whoami", "admin\n", 0, "code", False),
        TraceStep("hostname", "web-prod-01\n", 0, "code", False),
    ]
    passed, contr = check_whoami_and_hostname_never_change(trace_valid)
    assert passed is True
    assert contr == 0

    trace_invalid = [
        TraceStep("whoami", "admin\n", 0, "code", False),
        TraceStep("whoami", "root\n", 0, "model", False),
    ]
    passed, contr = check_whoami_and_hostname_never_change(trace_invalid)
    assert passed is False
    assert contr == 1


def test_run_benchmark_ours():
    """Verify run_benchmark produces valid aggregate metrics."""
    res = run_benchmark(mode="ours")
    assert res["mode"] == "ours"
    assert res["total_commands"] == 50
    assert res["pass_rate_pct"] == 100.0
    assert res["contradictions_per_100"] == 0.0
    assert res["share_answered_by_code"] > 90.0
    assert len(res["playbooks"]) == 5
