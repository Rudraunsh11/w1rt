# Final contract — exact names, never rename

Teammates code against these. Changes need all three teammates and a note in `docs/decisions/`.

## canarynet/state/session.py (Snehank)
```
class Session(session_id, user="admin", cwd="/home/admin", env, history, fs, src="")
    fs: dict  # absolute path -> {"type": "file" | "dir", "content": str}
    read_file(path) -> str | None
    write_file(path, content)
    delete(path) -> bool
    mkdir(path) -> bool
    listdir(path) -> list | None
    chdir(path) -> bool
    resolve(path) -> str        # absolute; handles relative, ., .., ~
    snapshot() -> dict          # short, for the model prompt

class Result(stdout, exit_code=0, state_changes=[])
```
Defaults: user `admin` (uid 1000, groups `admin sudo`), home `/home/admin`,
hostname `web-prod-01`, Ubuntu 22.04. Seeded: `/etc/passwd`, `/etc/hostname`,
`/etc/os-release`, `/home/admin/*`, `/var/log/auth.log`, `/var/www/html/index.html`.

## canarynet/router/router.py (Snehank)
```
run(session, line) -> str
```
shlex tokenize -> handle `>` / `>>` itself -> `HANDLERS[cmd](session, argv)` (argv excludes
the command name) -> else `llm.adapter.ask_model(...)`; `None` means
`bash: <cmd>: command not found` -> apply model `state_changes` exactly once ->
append line to `session.history` -> `logger.log_event(session_id, src, input, output,
answered_by, latency_ms, tags)` with `tags = attack.rules.tag(line)`.

## canarynet/canary/registry.py (Snehank)
```
plant(session) -> list[dict]
check(username, password, src) -> dict | None
```

## Model reply schema (validated before any state change)
```json
{"stdout": "str", "exit_code": 0,
 "state_changes": [{"op": "create_file|write_file|delete_file|chdir|set_env",
                    "path": "str", "content": "str (optional)"}]}
```
For `set_env`, `path` is the variable name and `content` is the value.

## Other owners
- Rudraunsh: `handlers.py`, `logger.py`, `rules.py`, `report.py`, `web.py`
- Aayush: `adapter.py`, `validator.py`, `guard.py`, `ssh.py`, bench playbooks and checkers

## Router facts (as built in S2)
- `ask_model(session, line)` returns a validated `Result` or `None` (confirmed from Aayush's
  adapter). The router also accepts a schema dict. The validator must NOT mutate the session;
  the router applies `state_changes` exactly once.
- Handlers: `HANDLERS[cmd](session, argv) -> Result`. Handlers change the session directly;
  the router ignores a handler's `state_changes`.
- `answered_by` is one of `code`, `model`, `not_found`, `model:handler_error`.
- `log_event` is called positionally in contract order.
- `snapshot()` keys: `user, host, os, cwd, home, cwd_listing, recent_commands`.

VERIFY with owners: the paths `canarynet/router/handlers.py`, `canarynet/attack/logger.py`,
`canarynet/attack/rules.py` (the router imports these; it uses stand-ins until they are merged).
