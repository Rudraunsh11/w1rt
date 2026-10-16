"""Small Linux command simulations over Session, never the host OS.

argv excludes the command name. The router owns shell parsing, redirection,
history insertion and model changes. Deterministic handlers return no proposed
changes: they use Session methods directly when they need to mutate state.
"""

import posixpath

from canarynet.state.session import Result


HANDLERS = {}


def command(name):
    """Register a handler without requiring edits to the router."""
    def register(function):
        if name in HANDLERS:
            raise ValueError(f"Handler already registered: {name}")
        HANDLERS[name] = function
        return function
    return register


def _result(text="", code=0):
    return Result(text, exit_code=code, state_changes=[])


def _error(command_name, operand, message):
    return _result(f"{command_name}: {operand}: {message}\n", 1)


def _kind(session, path):
    if session.read_file(path) is not None:
        return "file"
    if session.listdir(path) is not None:
        return "dir"
    return None


def _options(argv, allowed):
    flags, paths = set(), []
    parsing = True
    for argument in argv:
        if parsing and argument == "--":
            parsing = False
        elif parsing and argument.startswith("-") and argument != "-":
            for flag in argument[1:]:
                if flag not in allowed:
                    raise ValueError(flag)
                flags.add(flag)
        else:
            paths.append(argument)
    return flags, paths


def _listing(session, path, name, long_format):
    if not long_format:
        return name
    content = session.read_file(path)
    is_dir = content is None
    mode = "drwxr-xr-x" if is_dir else "-rw-r--r--"
    size = 4096 if is_dir else len(content.encode("utf-8"))
    # Synthetic metadata belongs to the decoy persona, never the real machine.
    return f"{mode} 1 {session.user} {session.user} {size:>5} Jan  1 00:00 {name}"


@command("ls")
def ls(session, argv):
    try:
        flags, paths = _options(argv, {"l", "a"})
    except ValueError as exc:
        return _error("ls", f"invalid option -- '{exc}'", "unsupported option")
    if len(paths) > 1:
        return _result("ls: multiple paths are not supported\n", 1)
    operand = paths[0] if paths else "."
    path = session.resolve(operand)
    kind = _kind(session, path)
    if kind is None:
        return _error("ls", f"cannot access '{operand}'", "No such file or directory")
    if kind == "file":
        return _result(_listing(session, path, operand, "l" in flags) + "\n")
    names = sorted(posixpath.basename(str(name).rstrip("/")) for name in session.listdir(path))
    if "a" in flags:
        names = [".", ".."] + [name for name in names if name not in {".", ".."}]
    else:
        names = [name for name in names if not name.startswith(".")]
    rows = [_listing(session, session.resolve(posixpath.join(path, name)), name, "l" in flags)
            for name in names]
    return _result("\n".join(rows) + ("\n" if rows else ""))


@command("cd")
def cd(session, argv):
    if len(argv) > 1:
        return _result("cd: too many arguments\n", 1)
    operand = argv[0] if argv else session.env.get("HOME", "/home/admin")
    if session.chdir(operand):
        return _result()
    kind = _kind(session, session.resolve(operand))
    return _error("cd", operand, "Not a directory" if kind == "file" else "No such file or directory")


@command("pwd")
def pwd(session, argv):
    if any(arg not in {"-L", "-P"} for arg in argv):
        return _result("pwd: unsupported argument\n", 1)
    return _result(session.cwd + "\n")


@command("cat")
def cat(session, argv):
    paths = list(argv)
    if paths and paths[0] == "--":
        paths.pop(0)
    if not paths:
        return _result("cat: standard input is not supported\n", 1)
    parts, code = [], 0
    for operand in paths:
        path = session.resolve(operand)
        content = session.read_file(path)
        if content is None:
            message = "Is a directory" if session.listdir(path) is not None else "No such file or directory"
            parts.append(f"cat: {operand}: {message}\n")
            code = 1
        else:
            parts.append(content)
    return _result("".join(parts), code)


@command("whoami")
def whoami(session, argv):
    if argv:
        return _result("whoami: extra operand\n", 1)
    return _result(session.user + "\n")


@command("id")
def id(session, argv):
    user = session.user
    if not argv:
        return _result(f"uid=1000({user}) gid=1000({user}) groups=1000({user}),27(sudo)\n")
    forms = {"-u": "1000", "-un": user, "-g": "1000", "-gn": user,
             "-G": "1000 27", "-Gn": f"{user} sudo"}
    if len(argv) == 1 and argv[0] in forms:
        return _result(forms[argv[0]] + "\n")
    return _result("id: unsupported argument\n", 1)


@command("uname")
def uname(session, argv):
    try:
        flags, operands = _options(argv, set("asnrvmo"))
    except ValueError:
        return _result("uname: unsupported option\n", 1)
    if operands:
        return _result("uname: extra operand\n", 1)
    if not flags:
        flags = {"s"}
    if "a" in flags:
        flags = set("snrvmo")
    fields = [("s", "Linux"), ("n", session.env.get("HOSTNAME", "web-prod-01")),
              ("r", "5.15.0-91-generic"), ("v", "#101-Ubuntu SMP"),
              ("m", "x86_64"), ("o", "GNU/Linux")]
    return _result(" ".join(value for key, value in fields if key in flags) + "\n")


@command("hostname")
def hostname(session, argv):
    if argv:
        return _result("hostname: setting hostname is not supported\n", 1)
    return _result(session.env.get("HOSTNAME", "web-prod-01") + "\n")

