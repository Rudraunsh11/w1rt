"""Command router: code handlers first, the local model only for unknown commands.

Visitor input is never executed. Every answer comes from Session state, a Python
handler, or a validated model reply whose state_changes are applied exactly once here.
"""
from __future__ import annotations

import importlib
import shlex
import sys
import time

from canarynet.state.session import Result, Session


STANDINS: list[str] = []  # teammate modules not merged yet; printed at startup


def _optional(module: str, attr: str, default):
    """Import a teammate's function; use a stand-in only while their file is not merged."""
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as err:
        if err.name != module:
            raise  # their file exists but something it imports is missing: fail loudly
        print(f"[router] {module} not merged yet, using stand-in", file=sys.stderr)
        STANDINS.append(module)
        return default
    return getattr(mod, attr)


# Contract dependencies. Module globals so tests can monkeypatch them.
HANDLERS = _optional("canarynet.router.handlers", "HANDLERS", {})
ask_model = _optional("canarynet.llm.adapter", "ask_model", lambda session, line: None)
log_event = _optional("canarynet.attack.logger", "log_event", lambda *args: None)
tag = _optional("canarynet.attack.rules", "tag", lambda line: [])

REDIRECTS = {">", ">>", ">&"}
PUNCT = set("();<>|&")  # shlex punctuation_chars
VALID_OPS = {"create_file", "write_file", "delete_file", "chdir", "set_env"}

# answered_by values (the benchmark counts these)
BY_CODE, BY_MODEL, BY_NOT_FOUND = "code", "model", "not_found"
BY_HANDLER_ERROR = "model:handler_error"


def run(session: Session, line: str) -> str:
    """Answer one visitor line. Returns text for the terminal (ends with a newline if non-empty)."""
    line = line.rstrip("\r\n")
    if not line.strip():
        return ""
    start = time.perf_counter()
    stdout, _exit_code, answered_by = _dispatch(session, line)
    if stdout and not stdout.endswith("\n"):
        stdout += "\n"
    session.history.append(line)
    latency_ms = round((time.perf_counter() - start) * 1000, 1)
    _log(session, line, stdout, answered_by, latency_ms)
    return stdout


# ---- dispatch --------------------------------------------------------------
def _tokenize(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _dispatch(session: Session, line: str) -> tuple[str, int, str]:
    try:
        tokens = _tokenize(line)
    except ValueError:  # unbalanced quotes
        return "bash: syntax error: unexpected end of file", 2, BY_CODE
    if not tokens:  # only a comment
        return "", 0, BY_CODE

    # Pipes, ;, &&, ||, subshells and command substitution: whole line goes to the model.
    compound = (any(t and set(t) <= PUNCT and t not in REDIRECTS for t in tokens)
                or "`" in line or "$(" in line)
    if compound:
        return _ask(session, line, tokens[0])

    try:
        argv, redirects = _split_redirects(tokens)
    except ValueError as err:
        return str(err), 2, BY_CODE

    if not argv:  # e.g. "> file" just creates/truncates the file
        return _redirect(session, redirects, "", 0), 0, BY_CODE

    cmd, args = argv[0], argv[1:]
    handler = HANDLERS.get(cmd)
    if handler is not None:
        try:
            stdout, exit_code = _unpack(handler(session, args))
            answered_by = BY_CODE
        except Exception as err:  # a handler bug must not kill the session
            print(f"[router] handler {cmd!r} crashed: {err!r}", file=sys.stderr)
            stdout, exit_code, _ = _ask(session, shlex.join(argv), cmd)
            answered_by = BY_HANDLER_ERROR
    else:
        stdout, exit_code, answered_by = _ask(session, shlex.join(argv), cmd)

    if redirects:
        stdout = _redirect(session, redirects, stdout, exit_code)
    return stdout, exit_code, answered_by


def _split_redirects(tokens: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Separate argv from stdout redirects. 2>... and >&... are dropped (no stderr model)."""
    argv, redirects, i = [], [], 0
    while i < len(tokens):
        tok = tokens[i]
        if tok not in REDIRECTS:
            argv.append(tok)
            i += 1
            continue
        if i + 1 >= len(tokens):
            raise ValueError("bash: syntax error near unexpected token `newline'")
        target = tokens[i + 1]
        is_stderr = bool(argv) and argv[-1] == "2"  # "2>" arrives as "2", ">"
        if is_stderr:
            argv.pop()
        if tok != ">&" and not is_stderr:
            redirects.append((tok, target))
        i += 2
    return argv, redirects


def _redirect(session: Session, redirects, stdout: str, exit_code: int) -> str:
    """Write stdout into the redirect target(s). Returns what the terminal should still show."""
    # A failing command's message is really stderr: it stays on screen, the file gets nothing.
    data, shown = (stdout, "") if exit_code == 0 else ("", stdout)
    if data and not data.endswith("\n"):
        data += "\n"
    last = len(redirects) - 1
    for i, (op, target) in enumerate(redirects):
        if target == "/dev/null":
            continue
        chunk = data if i == last else ""
        if op == ">>":
            chunk = (session.read_file(target) or "") + chunk
        if session.is_dir(target):
            return f"bash: {target}: Is a directory"
        if not session.write_file(target, chunk):
            return f"bash: {target}: No such file or directory"
    return shown


# ---- model path ------------------------------------------------------------
def _ask(session: Session, line: str, cmd: str) -> tuple[str, int, str]:
    try:
        reply = ask_model(session, line)
    except Exception as err:  # adapter should return None, but never crash the session
        print(f"[router] ask_model failed: {err!r}", file=sys.stderr)
        reply = None
    parsed = _parse_reply(reply)
    if parsed is None:
        return f"bash: {cmd}: command not found", 127, BY_NOT_FOUND
    stdout, exit_code, changes = parsed
    _apply_changes(session, changes)  # the only place model changes touch state
    return stdout, exit_code, BY_MODEL


def _parse_reply(reply) -> tuple[str, int, list] | None:
    """Accept a Result (adapter) or a dict (schema); None if the shape is wrong."""
    if isinstance(reply, Result):
        stdout, code, changes = reply.stdout, reply.exit_code, reply.state_changes
    elif isinstance(reply, dict):
        stdout, code, changes = reply.get("stdout"), reply.get("exit_code", 0), reply.get("state_changes", [])
    else:
        return None
    if not isinstance(stdout, str) or not isinstance(code, int) or not isinstance(changes, list):
        return None
    return stdout, code, changes


def _apply_changes(session: Session, changes: list) -> None:
    for ch in changes:
        if not isinstance(ch, dict) or ch.get("op") not in VALID_OPS:
            continue
        path, content = ch.get("path"), ch.get("content", "")
        if not isinstance(path, str) or not isinstance(content, str):
            continue
        op = ch["op"]
        if op in ("create_file", "write_file"):
            session.write_file(path, content)
        elif op == "delete_file":
            session.delete(path)
        elif op == "chdir":
            session.chdir(path)
        elif op == "set_env" and path.isidentifier():
            session.env[path] = content


# ---- helpers ---------------------------------------------------------------
def _unpack(res) -> tuple[str, int]:
    """Handlers return Result (contract); tolerate a bare string."""
    if isinstance(res, Result):
        return res.stdout, res.exit_code
    return str(res), 0


def _log(session: Session, line: str, output: str, answered_by: str, latency_ms: float) -> None:
    try:
        tags = tag(line)
    except Exception as err:
        print(f"[router] tag() failed: {err!r}", file=sys.stderr)
        tags = []
    try:
        # Positional, in contract order: (session_id, src, input, output, answered_by, latency_ms, tags)
        log_event(session.session_id, session.src, line, output, answered_by, latency_ms, tags)
    except Exception as err:
        print(f"[router] log_event failed: {err!r}", file=sys.stderr)
