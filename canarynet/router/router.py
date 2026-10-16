"""Router module (Contract stand-in for Snehank's router.py)."""

import shlex
from canarynet.state.session import Session


def run(session: Session, line: str) -> str:
    """Tokenizes, handles basic commands, appends to history, and returns stdout."""
    line = line.strip()
    if not line:
        return ""

    session.history.append(line)

    try:
        tokens = shlex.split(line)
    except Exception:
        tokens = line.split()

    if not tokens:
        return ""

    cmd = tokens[0]
    args = tokens[1:]

    # Basic built-ins for stand-in testing
    if cmd == "whoami":
        return f"{session.user}\n"
    elif cmd == "pwd":
        return f"{session.cwd}\n"
    elif cmd == "hostname":
        return "web-prod-01\n"
    elif cmd == "id":
        return f"uid=1000({session.user}) gid=1000({session.user}) groups=1000({session.user}),27(sudo)\n"
    elif cmd == "echo":
        return " ".join(args) + "\n"
    elif cmd == "cd":
        target = args[0] if args else f"/home/{session.user}"
        if session.chdir(target):
            return ""
        return f"bash: cd: {target}: No such file or directory\n"
    elif cmd == "ls":
        target = args[0] if args else session.cwd
        items = session.listdir(target)
        if items is None:
            return f"ls: cannot access '{target}': No such file or directory\n"
        return "  ".join(items) + ("\n" if items else "")
    else:
        # Stand-in default behavior per contract:
        # If None comes back from ask_model or validate, the router prints: bash: <cmd>: command not found.
        return f"bash: {cmd}: command not found\n"
