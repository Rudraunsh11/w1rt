"""CanaryNet Router module.

Handles tokenization, file redirection (> and >>), code handlers,
LLM fallback via ask_model, and applying state changes exactly once.
"""

import os
import re
import shlex
import time
from typing import Optional
from canarynet.llm import adapter
from canarynet.state.session import Session, Result


def _apply_state_changes(session: Session, changes: list) -> None:
    """Applies validated state changes from model reply to session state."""
    for change in changes:
        op = change.get("op")
        path = change.get("path")
        content = change.get("content", "")

        if op == "create_file" or op == "write_file":
            session.write_file(path, content)
        elif op == "delete_file":
            session.delete(path)
        elif op == "chdir":
            session.chdir(path)
        elif op == "set_env":
            session.env[path] = content


def run(session: Session, line: str, answered_by_out: Optional[list] = None) -> str:
    """Contract: run(session, line) -> str.

    Executes a command against session state, handles redirection, executes code handler,
    or falls back to ask_model, updating session state.
    """
    clean_line = line.strip()
    if not clean_line:
        return ""

    session.history.append(clean_line)

    # 1. Handle output redirection (> and >>)
    redirect_target = None
    append_mode = False

    if ">>" in clean_line:
        parts = clean_line.split(">>", 1)
        clean_line = parts[0].strip()
        redirect_target = parts[1].strip()
        append_mode = True
    elif ">" in clean_line:
        parts = clean_line.split(">", 1)
        clean_line = parts[0].strip()
        redirect_target = parts[1].strip()
        append_mode = False

    # 2. Tokenize command
    try:
        tokens = shlex.split(clean_line)
    except Exception:
        tokens = clean_line.split()

    if not tokens:
        return ""

    cmd = tokens[0]
    args = tokens[1:]

    output = ""
    answered_by = "code"

    # 3. Built-in Code Handlers
    if cmd == "whoami":
        output = f"{session.user}\n"
    elif cmd == "hostname":
        output = "web-prod-01\n"
    elif cmd == "pwd":
        output = f"{session.cwd}\n"
    elif cmd == "id":
        output = f"uid=1000({session.user}) gid=1000({session.user}) groups=1000({session.user}),27(sudo)\n"
    elif cmd == "echo":
        # Handle simple variable expansion like $HACK_VAR
        expanded_args = []
        for a in args:
            if a.startswith("$"):
                var_name = a[1:]
                expanded_args.append(session.env.get(var_name, ""))
            else:
                expanded_args.append(a)
        output = " ".join(expanded_args) + "\n"
    elif cmd == "cd":
        target = args[0] if args else f"/home/{session.user}"
        if not session.chdir(target):
            output = f"bash: cd: {target}: No such file or directory\n"
        else:
            output = ""
    elif cmd == "mkdir":
        if args:
            session.mkdir(args[0])
            output = ""
        else:
            output = "mkdir: missing operand\n"
    elif cmd == "rm":
        if args:
            target = args[-1]
            if session.delete(target):
                output = ""
            else:
                output = f"rm: cannot remove '{target}': No such file or directory\n"
        else:
            output = "rm: missing operand\n"
    elif cmd == "cat":
        if args:
            target = args[0]
            content = session.read_file(target)
            if content is not None:
                output = content if content.endswith("\n") else (content + "\n")
            else:
                output = f"cat: {target}: No such file or directory\n"
        else:
            output = ""
    elif cmd == "ls":
        # Handle ls and ls -l
        is_long = any(a.startswith("-") and "l" in a for a in args)
        target_args = [a for a in args if not a.startswith("-")]
        target = target_args[0] if target_args else session.cwd

        # Check if target is a file
        file_content = session.read_file(target)
        if file_content is not None:
            filename = target.split("/")[-1]
            if is_long:
                size = len(file_content.encode("utf-8"))
                output = f"-rw-r--r-- 1 {session.user} {session.user} {size} Oct 16 11:00 {filename}\n"
            else:
                output = f"{filename}\n"
        else:
            items = session.listdir(target)
            if items is None:
                output = f"ls: cannot access '{target}': No such file or directory\n"
            else:
                if is_long:
                    lines = [f"total {len(items) * 4}"]
                    for it in items:
                        lines.append(f"-rw-r--r-- 1 {session.user} {session.user} 1024 Oct 16 11:00 {it}")
                    output = "\n".join(lines) + "\n"
                else:
                    output = "  ".join(items) + ("\n" if items else "")
    elif cmd == "export":
        if args and "=" in args[0]:
            k, v = args[0].split("=", 1)
            session.env[k] = v
        output = ""
    else:
        # 4. Unknown command -> Fallback to Ollama ask_model
        answered_by = "model"
        res = adapter.ask_model(session, clean_line)
        if res is not None:
            output = res.stdout
            if res.state_changes:
                _apply_state_changes(session, res.state_changes)
        else:
            # Per contract: If None comes back from ask_model or validate:
            output = f"bash: {cmd}: command not found\n"

    # Handle Redirection to file
    if redirect_target:
        current_content = session.read_file(redirect_target) or "" if append_mode else ""
        new_content = current_content + output
        session.write_file(redirect_target, new_content)
        output = ""

    if answered_by_out is not None:
        answered_by_out.append(answered_by)

    return output
