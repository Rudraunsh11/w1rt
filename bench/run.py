"""CanaryNet consistency benchmark runner.

Supports:
- python -m bench.run --mode ours
- python -m bench.run --mode baseline

Measures multi-step consistency, contradiction rates, and inference latency
comparing CanaryNet Lite (code-owned state) against a last-10-command baseline.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from bench.checkers import TraceStep, evaluate_trace
from bench.playbooks import PLAYBOOKS
from canarynet.llm import guard, validator
from canarynet.llm.adapter import DEFAULT_MODEL, OLLAMA_CHAT_URL, SCHEMA, SYSTEM_PERSONA
from canarynet.router import router
from canarynet.state.session import Session

MODEL_SETTINGS = {
    "model": DEFAULT_MODEL,
    "temperature": 0.0,
    "seed": 42,
    "num_predict": 512,
    "format": "json_schema",
    "warmup_policy": "manual: run `ollama run qwen2.5:1.5b \"say ok\"` before measuring (not performed by bench.run)",
}


def get_host_metadata() -> Dict[str, Any]:
    """Dynamically collects host system metadata (no hardcoded host strings)."""
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "python_version": sys.version.split()[0],
        "system": platform.system(),
        "release": platform.release(),
    }


def run_playbook_ours(
    playbook_name: str,
    commands: List[str],
) -> Tuple[List[TraceStep], List[float]]:
    """Runs a playbook under CanaryNet Lite ('ours' mode with code-owned virtual state)."""
    if "canarynet.router.handlers" in getattr(router, "STANDINS", []):
        sys.exit("handlers.py not merged: 'ours' mode would not measure the product")

    session = Session(session_id=f"bench-{playbook_name}", user="admin")
    trace: List[TraceStep] = []
    latencies: List[float] = []

    last_observed: Dict[str, Any] = {}

    def _observer_hook(s: Session, line: str, stdout: str, exit_code: int, answered_by: str, latency_ms: float) -> None:
        last_observed["exit_code"] = exit_code
        last_observed["answered_by"] = answered_by
        last_observed["latency_ms"] = latency_ms

    router.set_observer_hook(_observer_hook)
    try:
        for cmd in commands:
            fs_before = dict(session.fs)
            cwd_before = session.cwd
            env_before = dict(session.env)
            last_observed.clear()

            t0 = time.perf_counter()
            out = router.run(session, cmd)
            client_elapsed_ms = (time.perf_counter() - t0) * 1000.0

            measured_lat = last_observed.get("latency_ms", round(client_elapsed_ms, 2))
            latencies.append(measured_lat)

            answered_by = last_observed.get("answered_by", "code")
            exit_code = last_observed.get("exit_code", 0 if not out.startswith("bash:") else 127)
            state_changed = (
                session.fs != fs_before
                or session.cwd != cwd_before
                or session.env != env_before
            )

            trace.append(
                TraceStep(
                    cmd=cmd,
                    stdout=out,
                    exit_code=exit_code,
                    answered_by=answered_by,
                    state_changed=state_changed,
                )
            )
    finally:
        router.set_observer_hook(None)

    return trace, latencies


class BaselineInferenceRunner:
    """Real measured inference baseline (last-10-command dialogue window).
    
    Window definition:
    - Initial message: SYSTEM_PERSONA (fixed Ubuntu 22.04 web-prod-01 persona).
    - Dialogue history: Exactly the last 10 completed (user: cmd, assistant: reply) turns.
      Turns older than 10 are evicted.
    - Current message: user: guard.wrap_input(cmd) (aligned with production adapter prompt delimiters).
    - NO persistent mutable Session state is leaked into prompt (no fs, cwd, or file list).
    - Uses exact same model tag, decoding settings, and schema validation as ours.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        client: Optional[httpx.Client] = None,
        timeout: float = 20.0,
        url: str = OLLAMA_CHAT_URL,
    ):
        self.model = model
        self.client = client
        self.timeout = timeout
        self.url = url
        self.history: List[Tuple[str, str]] = []  # List of (cmd, stdout)
        self.model_calls: int = 0
        self.rejections: int = 0
        self.timeouts: int = 0

    def query(self, cmd: str) -> Tuple[str, int, float]:
        """Queries local Ollama using last-10-commands context window and measures inference latency."""
        # 1. Build messages with sliding window of last 10 completed pairs
        window = self.history[-10:]
        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PERSONA}]
        for past_cmd, past_out in window:
            messages.append({"role": "user", "content": past_cmd})
            messages.append({
                "role": "assistant",
                "content": json.dumps({"stdout": past_out, "exit_code": 0, "state_changes": []}),
            })
        messages.append({"role": "user", "content": guard.wrap_input(cmd)})

        payload = {
            "model": self.model,
            "messages": messages,
            "format": SCHEMA,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "seed": 42,
                "num_predict": 512,
            },
        }

        own_client = False
        client = self.client
        if client is None:
            client = httpx.Client(timeout=self.timeout)
            own_client = True

        t0 = time.perf_counter()
        try:
            self.model_calls += 1
            resp = client.post(self.url, json=payload)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            if resp.status_code != 200:
                self.rejections += 1
                cmd_name = cmd.split()[0] if cmd.split() else "cmd"
                stdout = f"bash: {cmd_name}: command not found\n"
                exit_code = 127
            else:
                data = resp.json()
                raw_content = data.get("message", {}).get("content", "")
                try:
                    parsed = json.loads(raw_content)
                    # Same rejection policy as production: adapter.ask_model -> validator.validate
                    checked = validator.validate(parsed, None)
                    if checked is not None:
                        stdout = checked.stdout
                        if stdout and not stdout.endswith("\n"):
                            stdout += "\n"  # same as router._ask for model replies
                        exit_code = checked.exit_code
                    else:
                        self.rejections += 1
                        cmd_name = cmd.split()[0] if cmd.split() else "cmd"
                        stdout = f"bash: {cmd_name}: command not found\n"
                        exit_code = 127
                except Exception:
                    self.rejections += 1
                    cmd_name = cmd.split()[0] if cmd.split() else "cmd"
                    stdout = f"bash: {cmd_name}: command not found\n"
                    exit_code = 127

        except httpx.TimeoutException:
            self.timeouts += 1
            latency_ms = (time.perf_counter() - t0) * 1000.0
            cmd_name = cmd.split()[0] if cmd.split() else "cmd"
            stdout = f"bash: {cmd_name}: command timed out\n"
            exit_code = 124
        except Exception as exc:
            raise RuntimeError(
                f"Ollama inference failed at {self.url}. Ensure Ollama is running and {self.model} is loaded: {exc}"
            ) from exc
        finally:
            if own_client:
                client.close()

        self.history.append((cmd, stdout))
        return stdout, exit_code, latency_ms


class CannedBaselineSimulator:
    """CANNED TEST FIXTURE ONLY: For offline tests when Ollama is unavailable.
    
    MUST NOT be used for measured benchmark numbers.
    """

    def __init__(self):
        self.history: List[Tuple[str, str]] = []

    def query(self, cmd: str) -> Tuple[str, int, float]:
        self.history.append((cmd, ""))
        if cmd == "pwd":
            return "/home/admin\n", 0, 1.0
        return f"{cmd}: ok\n", 0, 1.0


def run_playbook_baseline(
    playbook_name: str,
    commands: List[str],
    runner: Optional[BaselineInferenceRunner] = None,
) -> Tuple[List[TraceStep], List[float]]:
    """Runs a playbook under the last-10-commands baseline mode using real Ollama inference."""
    if runner is None:
        runner = BaselineInferenceRunner()

    trace: List[TraceStep] = []
    latencies: List[float] = []

    for cmd in commands:
        stdout, exit_code, latency_ms = runner.query(cmd)
        latencies.append(latency_ms)
        trace.append(
            TraceStep(
                cmd=cmd,
                stdout=stdout,
                exit_code=exit_code,
                answered_by="model",
                state_changed=False,
            )
        )

    return trace, latencies


def is_ollama_reachable(url: str = OLLAMA_CHAT_URL) -> bool:
    """Checks if loopback Ollama is reachable."""
    try:
        base_url = url.rsplit("/", 2)[0]
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{base_url}/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


def run_benchmark(
    mode: str = "ours",
    runner: Optional[BaselineInferenceRunner] = None,
) -> Dict[str, Any]:
    """Executes all 5 playbooks and computes aggregate metrics."""
    if mode == "baseline" and runner is None:
        if not is_ollama_reachable():
            raise RuntimeError(
                "Ollama service is unreachable at 127.0.0.1:11434. "
                "Measured baseline requires a live local Ollama instance with model qwen2.5:1.5b. "
                "No fabricated benchmark numbers are permitted."
            )

    total_commands = 0
    all_latencies: List[float] = []
    code_answered_count = 0
    model_answered_count = 0
    total_contradictions = 0
    total_applicable_checkers = 0
    total_passed_checkers = 0

    playbook_results: Dict[str, Any] = {}
    raw_traces: Dict[str, Any] = {}

    for name, cmds in PLAYBOOKS.items():
        if mode == "ours":
            trace, lats = run_playbook_ours(name, cmds)
        else:
            trace, lats = run_playbook_baseline(name, cmds, runner=runner)

        eval_res = evaluate_trace(trace)

        total_commands += len(cmds)
        all_latencies.extend(lats)
        code_answered_count += sum(1 for step in trace if step.answered_by == "code")
        model_answered_count += sum(1 for step in trace if step.answered_by in ("model", "not_found", "model:handler_error"))
        total_contradictions += eval_res["total_contradictions"]
        total_applicable_checkers += eval_res["applicable_checkers_count"]
        total_passed_checkers += eval_res["passed_checkers_count"]

        playbook_results[name] = {
            "commands": len(cmds),
            "pass_rate_pct": eval_res["pass_rate_pct"],
            "contradictions": eval_res["total_contradictions"],
            "applicable_checkers": eval_res["applicable_checkers_count"],
            "passed_checkers": eval_res["passed_checkers_count"],
            "status": eval_res["status"],
        }
        raw_traces[name] = [
            {
                "cmd": step.cmd,
                "stdout": step.stdout,
                "exit_code": step.exit_code,
                "answered_by": step.answered_by,
                "state_changed": step.state_changed,
            }
            for step in trace
        ]

    pass_rate_pct = (
        round((total_passed_checkers / total_applicable_checkers) * 100.0, 1)
        if total_applicable_checkers > 0
        else 0.0
    )
    contradictions_per_100 = (
        round((total_contradictions / total_commands) * 100.0, 1)
        if total_commands > 0
        else 0.0
    )
    share_code_pct = (
        round((code_answered_count / total_commands) * 100.0, 1)
        if total_commands > 0
        else 0.0
    )
    median_lat_ms = (
        round(statistics.median(all_latencies), 2)
        if all_latencies
        else 0.0
    )

    results = {
        "mode": mode,
        "mode_description": "CanaryNet Lite (code-owned state)" if mode == "ours" else "last-10-command baseline",
        "total_commands": total_commands,
        "pass_rate_pct": pass_rate_pct,
        "contradictions_per_100": contradictions_per_100,
        "share_answered_by_code": share_code_pct,
        "median_latency_ms": median_lat_ms,
        "model_settings": MODEL_SETTINGS,
        "host_metadata": get_host_metadata(),
        "playbooks": playbook_results,
        "raw_traces": raw_traces,
    }

    return results


def print_markdown_table(res: Dict[str, Any]) -> None:
    """Prints benchmark results table in clean GitHub-flavored markdown."""
    host = res["host_metadata"]
    print("\n### CanaryNet Lite Consistency Benchmark Results")
    print(f"**Mode**: `{res['mode_description']}` | **Model**: `{res['model_settings']['model']}`")
    print(f"**Host**: `{host['platform']}` ({host['processor']}), Python `{host['python_version']}`\n")
    print("| Metric | Value | Definition / Target |")
    print("| :--- | :--- | :--- |")
    print(f"| **Pass Rate** | {res['pass_rate_pct']}% | Applicable checkers passing (no contradictions) |")
    print(f"| **Contradictions / 100 cmds** | {res['contradictions_per_100']} | Rate of state contradictions per 100 commands |")
    print(f"| **Share Answered by Code** | {res['share_answered_by_code']}% | Deterministic virtual filesystem handlers |")
    print(f"| **Median Latency** | {res['median_latency_ms']} ms | Response budget per command |")
    print(f"| **Total Commands Tested** | {res['total_commands']} | 5 playbooks of >=20 commands each |")
    print("\n#### Playbook Breakdown:")
    for pb, data in res["playbooks"].items():
        print(
            f"- `{pb}`: Pass Rate = {data['pass_rate_pct']}%, "
            f"Contradictions = {data['contradictions']}, "
            f"Checkers = {data['passed_checkers']}/{data['applicable_checkers']} ({data['status']})"
        )
    print()


def write_results(results: Dict[str, Any], path: str) -> str:
    """Persist the full result (metrics, settings, host metadata, raw traces) as JSON."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    return path


def main(argv: Optional[List[str]] = None):
    parser = argparse.ArgumentParser(description="CanaryNet consistency benchmark")
    parser.add_argument(
        "--mode",
        choices=["ours", "baseline"],
        default="ours",
        help="Benchmark mode: 'ours' (state-backed) or 'baseline' (last-10-command baseline)",
    )
    parser.add_argument("--out", default=None, help="JSON output path (default bench/results_<mode>.json)")
    args = parser.parse_args(argv)
    results = run_benchmark(mode=args.mode)
    print_markdown_table(results)
    path = write_results(results, args.out or os.path.join("bench", f"results_{args.mode}.json"))
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
