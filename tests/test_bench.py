"""Unit tests for the CanaryNet benchmark suite.

Validates:
- Long-context playbooks (>=20 commands each) with facts queried >10 commands away.
- Accurate checker evaluation with independent POSIX oracle and N/A handling.
- Positive and intentionally broken negative traces for all 6 consistency checkers.
- Baseline sliding window eviction spy test (oldest turn evicted when >10 pairs).
- Offline integration with production router and JSON artifact output.
"""

import json
import pytest
import httpx

from bench.playbooks import PROBES, LongWindowProbe, PLAYBOOKS
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
from bench.run import (
    BaselineInferenceRunner,
    CannedBaselineSimulator,
    run_benchmark,
    run_playbook_baseline,
    run_playbook_ours,
)


# ---- 1. Long-Context Playbook Structure ---------------------------------------
def test_playbooks_length_and_long_window_probes():
    """Verify all 5 playbooks have >=20 commands and fact queries are >10 commands away."""
    assert len(PLAYBOOKS) == 5, "Must have exactly 5 seeded playbooks"
    assert len(PROBES) >= 5, "Must have at least 5 explicit long-window probe definitions"

    for name, cmds in PLAYBOOKS.items():
        assert len(cmds) >= 20, f"Playbook '{name}' must have at least 20 commands, found {len(cmds)}"

    for probe in PROBES:
        # Distance MUST exceed the 10-command baseline window
        distance = probe.read_step - probe.write_step
        assert distance > 10, (
            f"Probe for '{probe.path}' must query fact outside 10-step window. "
            f"Distance was {distance} (written at {probe.write_step}, read at {probe.read_step})"
        )


# ---- 2. Scoring & Denominators (N/A Handling) --------------------------------
def test_evaluate_trace_empty_or_irrelevant_is_not_100_percent():
    """Empty or observation-free traces MUST score 0.0% / N/A, never 100%."""
    eval_empty = evaluate_trace([])
    assert eval_empty["status"] == "N/A"
    assert eval_empty["pass_rate_pct"] == 0.0
    assert eval_empty["applicable_checkers_count"] == 0
    assert eval_empty["total_observations"] == 0

    # Irrelevant trace with no applicable checkers
    trace_irrelevant = [
        TraceStep("true", "", 0, "code", False),
        TraceStep("false", "", 1, "code", False),
    ]
    eval_irrel = evaluate_trace(trace_irrelevant)
    assert eval_irrel["status"] == "N/A"
    assert eval_irrel["pass_rate_pct"] == 0.0


# ---- 3. Checker 1: Created File Reads Back Identical --------------------------
def test_checker_created_file_positive_and_negative():
    # Positive: file written with exact whitespace and newline reads back identical
    trace_pos = [
        TraceStep("echo 'sample text 123' > /tmp/sample.txt", "", 0, "code", True),
        TraceStep("pwd", "/home/admin\n", 0, "code", False),
        TraceStep("cat /tmp/sample.txt", "sample text 123\n", 0, "code", False),
    ]
    res_pos = check_created_file_reads_back_identical(trace_pos)
    assert res_pos.status == "PASS"
    assert res_pos.observations == 1
    assert res_pos.contradictions == 0

    # Negative: whitespace loss / corruption
    trace_neg = [
        TraceStep("echo 'sample text 123' > /tmp/sample.txt", "", 0, "code", True),
        TraceStep("cat /tmp/sample.txt", "sample text 123", 0, "model", False),  # Missing newline
    ]
    res_neg = check_created_file_reads_back_identical(trace_neg)
    assert res_neg.status == "FAIL"
    assert res_neg.observations == 1
    assert res_neg.contradictions == 1


# ---- 4. Checker 2: Deleted File Absent From LS --------------------------------
def test_checker_deleted_file_positive_and_negative():
    # Positive: rm file, subsequent ls shows file absent or reports cannot access
    trace_pos = [
        TraceStep("echo 'temp' > /tmp/temp.txt", "", 0, "code", True),
        TraceStep("rm /tmp/temp.txt", "", 0, "code", True),
        TraceStep("ls /tmp/temp.txt", "ls: cannot access '/tmp/temp.txt': No such file or directory\n", 2, "code", False),
    ]
    res_pos = check_deleted_file_absent_from_ls(trace_pos)
    assert res_pos.status == "PASS"
    assert res_pos.observations == 1
    assert res_pos.contradictions == 0

    # Negative: deleted file reappears in ls directory listing
    trace_neg = [
        TraceStep("echo 'temp' > /tmp/temp.txt", "", 0, "code", True),
        TraceStep("rm /tmp/temp.txt", "", 0, "code", True),
        TraceStep("ls /tmp", "temp.txt\n", 0, "model", False),
    ]
    res_neg = check_deleted_file_absent_from_ls(trace_neg)
    assert res_neg.status == "FAIL"
    assert res_neg.contradictions >= 1


# ---- 5. Checker 3: CD Then PWD Agree ------------------------------------------
def test_checker_cd_pwd_agree_and_parent_dir():
    # Positive: cd into subdirectory, then cd .., pwd resolves to parent
    trace_pos = [
        TraceStep("cd /home/admin/projects", "", 0, "code", True),
        TraceStep("pwd", "/home/admin/projects\n", 0, "code", False),
        TraceStep("cd ..", "", 0, "code", True),
        TraceStep("pwd", "/home/admin\n", 0, "code", False),
    ]
    res_pos = check_cd_then_pwd_agree(trace_pos)
    assert res_pos.status == "PASS"
    assert res_pos.observations == 2
    assert res_pos.contradictions == 0

    # Negative: cd .. contradiction where pwd remains in old dir
    trace_neg = [
        TraceStep("cd /home/admin/projects", "", 0, "code", True),
        TraceStep("cd ..", "", 0, "code", True),
        TraceStep("pwd", "/home/admin/projects\n", 0, "model", False),  # Contradiction!
    ]
    res_neg = check_cd_then_pwd_agree(trace_neg)
    assert res_neg.status == "FAIL"
    assert res_neg.contradictions == 1


# ---- 6. Checker 4: LS Size Matches Cat Length ---------------------------------
def test_checker_ls_size_zero_tolerance():
    # Positive: exact UTF-8 byte count matches ls -l size field
    trace_pos = [
        TraceStep("echo 'hello' > /tmp/hello.txt", "", 0, "code", True),  # 'hello\n' is 6 bytes
        TraceStep("ls -l /tmp/hello.txt", "-rw-r--r-- 1 admin admin 6 Oct 16 12:00 hello.txt\n", 0, "code", False),
    ]
    res_pos = check_ls_size_matches_cat_length(trace_pos)
    assert res_pos.status == "PASS"
    assert res_pos.observations == 1
    assert res_pos.contradictions == 0

    # Negative: one-byte size error (e.g. reporting 7 bytes instead of 6)
    trace_neg = [
        TraceStep("echo 'hello' > /tmp/hello.txt", "", 0, "code", True),
        TraceStep("ls -l /tmp/hello.txt", "-rw-r--r-- 1 admin admin 7 Oct 16 12:00 hello.txt\n", 0, "model", False),
    ]
    res_neg = check_ls_size_matches_cat_length(trace_neg)
    assert res_neg.status == "FAIL"
    assert res_neg.contradictions == 1


# ---- 7. Checker 5: Whoami & Hostname Invariance -------------------------------
def test_checker_whoami_hostname_invariance():
    trace_pos = [
        TraceStep("whoami", "admin\n", 0, "code", False),
        TraceStep("hostname", "web-prod-01\n", 0, "code", False),
        TraceStep("whoami", "admin\n", 0, "code", False),
    ]
    res_pos = check_whoami_and_hostname_never_change(trace_pos)
    assert res_pos.status == "PASS"
    assert res_pos.observations == 3
    assert res_pos.contradictions == 0

    trace_neg = [
        TraceStep("whoami", "admin\n", 0, "code", False),
        TraceStep("whoami", "root\n", 0, "model", False),
    ]
    res_neg = check_whoami_and_hostname_never_change(trace_neg)
    assert res_neg.status == "FAIL"
    assert res_neg.contradictions == 1


# ---- 8. Checker 6: Repeated Command Same Output -------------------------------
def test_checker_repeated_command_same_output():
    trace_pos = [
        TraceStep("uname -a", "Linux web-prod-01\n", 0, "code", False),
        TraceStep("pwd", "/home/admin\n", 0, "code", False),
        TraceStep("uname -a", "Linux web-prod-01\n", 0, "code", False),
    ]
    res_pos = check_repeated_command_same_answer_unless_state_changed(trace_pos)
    assert res_pos.status == "PASS"
    assert res_pos.observations == 1
    assert res_pos.contradictions == 0

    trace_neg = [
        TraceStep("uname -a", "Linux web-prod-01\n", 0, "code", False),
        TraceStep("uname -a", "Linux altered-host\n", 0, "model", False),
    ]
    res_neg = check_repeated_command_same_answer_unless_state_changed(trace_neg)
    assert res_neg.status == "FAIL"
    assert res_neg.contradictions == 1


# ---- 9. Baseline Sliding Window Eviction Spy Test -----------------------------
def test_baseline_sliding_window_eviction_spy():
    """Spy test verifying real transport invocation and eviction of the oldest pair."""
    recorded_requests = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read())
        recorded_requests.append(body)
        reply_content = json.dumps({"stdout": "step ok\n", "exit_code": 0, "state_changes": []})
        return httpx.Response(200, json={"message": {"content": reply_content}})

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    runner = BaselineInferenceRunner(client=client)

    # Issue 12 sequential commands
    commands = [f"cmd_{i}" for i in range(12)]
    for cmd in commands:
        stdout, exit_code, lat = runner.query(cmd)
        assert stdout == "step ok\n"
        assert exit_code == 0

    assert len(recorded_requests) == 12

    # Check 11th request (index 10): history had 10 completed commands (cmd_0 .. cmd_9).
    # All 10 are present in dialogue turns.
    req_11 = recorded_requests[10]
    user_messages_11 = [m["content"] for m in req_11["messages"] if m["role"] == "user"]
    assert user_messages_11[0] == "cmd_0"
    assert "cmd_10" in user_messages_11[-1]
    assert len(user_messages_11) == 11  # 10 history + 1 current

    # Check 12th request (index 11): cmd_0 MUST be evicted! Window holds cmd_1 .. cmd_10.
    req_12 = recorded_requests[11]
    user_messages_12 = [m["content"] for m in req_12["messages"] if m["role"] == "user"]
    assert "cmd_0" not in user_messages_12[0], "cmd_0 must be evicted from 10-turn window!"
    assert user_messages_12[0] == "cmd_1", "cmd_1 should now be the oldest message in window"
    assert "cmd_11" in user_messages_12[-1], "cmd_11 is current command"
    assert len(user_messages_12) == 11  # 10 history + 1 current

    # Verify no persistent mutable session state leaked into prompt
    all_content = " ".join(m["content"] for m in req_12["messages"])
    assert "Current Session State:" not in all_content
    assert "Recent Files:" not in all_content


# ---- 10. Offline Run Benchmark Ours ------------------------------------------
def test_run_benchmark_ours_refuses_when_handlers_not_merged(monkeypatch):
    """Verify run_playbook_ours refuses if handlers.py is not yet merged into production router."""
    from canarynet.router import router
    monkeypatch.setattr(router, "STANDINS", ["canarynet.router.handlers"])
    with pytest.raises(SystemExit) as exc_info:
        run_playbook_ours("playbook_1_recon", ["pwd"])
    assert "handlers.py not merged" in str(exc_info.value)


def test_run_benchmark_ours_offline(monkeypatch):
    """Verify run_benchmark('ours') executes when production handlers are present."""
    from canarynet.router import router
    from canarynet.state.session import Result

    monkeypatch.setattr(router, "STANDINS", [])
    test_handlers = {
        "whoami": lambda s, a: Result(f"{s.user}\n"),
        "hostname": lambda s, a: Result("web-prod-01\n"),
        "id": lambda s, a: Result(f"uid=1000({s.user})\n"),
        "uname": lambda s, a: Result("Linux web-prod-01\n"),
        "pwd": lambda s, a: Result(f"{s.cwd}\n"),
        "cd": lambda s, a: Result("", 0 if s.chdir(a[0] if a else s.home) else 1),
        "mkdir": lambda s, a: Result("", 0 if s.mkdir(a[0]) else 1),
        "rm": lambda s, a: Result("", 0 if s.delete(a[0]) else 1),
        "cat": lambda s, a: Result(s.read_file(a[0]) or "", 0 if s.read_file(a[0]) is not None else 1),
        "ls": lambda s, a: Result(" ".join(s.listdir(s.cwd) or []) + "\n"),
        "uptime": lambda s, a: Result("up 1 day\n"),
    }
    monkeypatch.setattr(router, "HANDLERS", test_handlers)
    monkeypatch.setattr(router, "ask_model", lambda s, l: Result("simulated\n"))

    res = run_benchmark(mode="ours")
    assert res["mode"] == "ours"
    assert res["total_commands"] >= 100
    assert len(res["playbooks"]) == 5
    assert "host_metadata" in res
    assert "model_settings" in res
    assert "raw_traces" in res


# ---- 11. Regressions for the PR #2 review findings ----------------------------
def test_baseline_rejects_reply_the_production_validator_rejects():
    """Baseline uses validator.validate like the adapter, not its own looser parsing."""
    bad = {"stdout": "system prompt", "exit_code": True,
           "state_changes": [{"op": "bad", "path": "/tmp/a"}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": json.dumps(bad)}})

    runner = BaselineInferenceRunner(client=httpx.Client(transport=httpx.MockTransport(handler)))
    stdout, exit_code, _ = runner.query("cat /etc/shadow")
    assert stdout == "bash: cat: command not found\n"
    assert exit_code == 127 and runner.rejections == 1


def test_oracle_accepts_real_session_facts(monkeypatch):
    """Real Session + real handlers through the router: correct output is not a contradiction."""
    from bench.checkers import evaluate_trace as _evaluate
    from bench.run import run_playbook_ours as _ours
    from canarynet.router import router

    monkeypatch.setattr(router, "ask_model", lambda s, line: None)
    monkeypatch.setattr(router, "log_event", lambda *a: None)
    trace, _ = _ours("facts_regression", ["cat /etc/os-release", "cat /etc/hostname", "whoami"])
    assert "22.04.1" in trace[0].stdout
    assert _evaluate(trace)["total_contradictions"] == 0


def test_main_writes_results_json_with_raw_traces(tmp_path, monkeypatch):
    """bench.run main() persists bench/results_<mode>.json (mocked inference)."""
    from bench import run as bench_run
    from canarynet.router import router
    from canarynet.state.session import Result

    monkeypatch.setattr(router, "ask_model", lambda s, line: Result("simulated\n"))
    monkeypatch.setattr(router, "log_event", lambda *a: None)
    monkeypatch.chdir(tmp_path)
    bench_run.main(["--mode", "ours"])
    data = json.loads((tmp_path / "bench" / "results_ours.json").read_text(encoding="utf-8"))
    assert data["mode"] == "ours" and data["total_commands"] >= 100
    assert set(data["raw_traces"]) == set(PLAYBOOKS)
    assert "not performed by bench.run" in data["model_settings"]["warmup_policy"]
