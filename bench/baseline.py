"""S5 baseline mode: same model, persona, schema and guard as canarynet.llm.adapter,
but the only memory is the last 10 commands with their outputs. No Session, no code
handlers. This is the "last 10 commands" baseline, not a test of any other project.
"""
from __future__ import annotations

import json
import time

import httpx

from bench.checkers import TraceStep
from canarynet.llm import adapter, guard

HISTORY_WINDOW = 10
OUTPUT_CHARS = 400  # per remembered output, keeps the prompt inside a small context window
# Commands that would change state in a real shell. Marking them keeps the
# "same answer unless state changed" check lenient to the baseline.
MUTATING = {"cd", "rm", "rmdir", "mkdir", "touch", "mv", "cp", "export", "unset", "chmod", "chown"}


def _mutates(cmd: str) -> bool:
    words = cmd.split()
    return bool(words) and (words[0] in MUTATING or ">" in cmd)


def ask_baseline(history: list[tuple[str, str]], line: str, client=None) -> tuple[str, int] | None:
    """Ask the model with only the last HISTORY_WINDOW (command, output) pairs as memory."""
    recent = history[-HISTORY_WINDOW:]
    transcript = "\n".join(f"$ {c}\n{o[:OUTPUT_CHARS]}" for c, o in recent) or "(none)"
    payload = {
        "model": adapter.DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": adapter.SYSTEM_PERSONA},
            {"role": "user", "content": (
                f"Previous commands and outputs (last {HISTORY_WINDOW}):\n{transcript}\n\n"
                f"Visitor Input:\n{guard.wrap_input(line)}")},
        ],
        "format": adapter.SCHEMA,
        "stream": False,
        # Same decoding options as adapter.ask_model (VERIFY they still match after edits there).
        "options": {"temperature": 0.0, "seed": 42, "num_predict": 512},
    }
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=adapter.TIMEOUT_SECONDS)
    try:
        response = client.post(adapter.OLLAMA_CHAT_URL, json=payload)
        if response.status_code != 200:
            return None
        reply = json.loads(response.json().get("message", {}).get("content", ""))
    except (httpx.HTTPError, ValueError, AttributeError):
        return None
    finally:
        if own_client:
            client.close()
    if not isinstance(reply, dict) or not isinstance(reply.get("stdout"), str):
        return None
    exit_code = reply.get("exit_code", 0)
    return reply["stdout"], exit_code if isinstance(exit_code, int) else 0


def run_playbook_baseline(playbook_name: str, commands: list[str], client=None):
    """Same return shape as bench.run.run_playbook_ours: (trace, latencies_ms)."""
    history: list[tuple[str, str]] = []
    trace: list[TraceStep] = []
    latencies: list[float] = []
    for cmd in commands:
        t0 = time.perf_counter()
        res = ask_baseline(history, cmd, client)
        if res is None:
            out, code, by = f"bash: {cmd.split()[0]}: command not found\n", 127, "not_found"
        else:
            out, code = res
            by = "model"
            if out and not out.endswith("\n"):
                out += "\n"
        latencies.append((time.perf_counter() - t0) * 1000.0)
        history.append((cmd, out))
        trace.append(TraceStep(cmd=cmd, stdout=out, exit_code=code, answered_by=by,
                               state_changed=_mutates(cmd)))
    return trace, latencies
