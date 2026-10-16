"""Canary registry: plant fake credentials in a session and detect when they are reused.

All values are generated per session with `secrets`; nothing here is a real credential.
The registry lives in memory for the life of the process.
"""
from __future__ import annotations

import secrets
import string
import threading
import time

from canarynet.state.session import Session

# Rule-based ATT&CK techniques for a canary reuse:
# T1552.001 Unsecured Credentials: Credentials In Files; T1078 Valid Accounts.
REUSE_TAGS = ["T1552.001", "T1078"]

_LOCK = threading.Lock()
_BY_VALUE: dict[str, dict] = {}     # any reusable value (password, key id, secret) -> record
_BY_SESSION: dict[str, list] = {}   # session_id -> records planted in it

_UPPER_DIGITS = string.ascii_uppercase + string.digits
_SECRET_CHARS = string.ascii_letters + string.digits + "/+"


def _rand(chars: str, n: int) -> str:
    return "".join(secrets.choice(chars) for _ in range(n))


def _env_file(db_user: str, db_pass: str) -> str:
    return (
        "APP_NAME=webprod\nAPP_ENV=production\nAPP_DEBUG=false\n\n"
        "DB_CONNECTION=mysql\nDB_HOST=127.0.0.1\nDB_PORT=3306\n"
        f"DB_DATABASE=webprod\nDB_USERNAME={db_user}\nDB_PASSWORD={db_pass}\n"
    )


def _aws_file(key_id: str, secret: str) -> str:
    return f"[default]\naws_access_key_id = {key_id}\naws_secret_access_key = {secret}\n"


def plant(session: Session) -> list[dict]:
    """Write fake .env and ~/.aws/credentials into the session's fs. Idempotent per session."""
    with _LOCK:
        if session.session_id in _BY_SESSION:
            return [dict(r) for r in _BY_SESSION[session.session_id]]

    planted = []
    now = time.time()

    db_user, db_pass = "webapp", _rand(string.ascii_letters + string.digits, 20)
    env_path = "/var/www/html/.env"
    if session.write_file(env_path, _env_file(db_user, db_pass)):
        planted.append({"kind": "env_db", "path": env_path,
                        "username": db_user, "secret": db_pass, "lookup": [db_pass]})

    key_id, aws_secret = "AKIA" + _rand(_UPPER_DIGITS, 16), _rand(_SECRET_CHARS, 40)
    aws_dir = session.resolve("~/.aws")
    session.mkdir(aws_dir)  # False if it already exists; fine
    aws_path = aws_dir + "/credentials"
    if session.write_file(aws_path, _aws_file(key_id, aws_secret)):
        planted.append({"kind": "aws", "path": aws_path,
                        "username": key_id, "secret": aws_secret, "lookup": [key_id, aws_secret]})

    records = []
    with _LOCK:
        for item in planted:
            lookup = item.pop("lookup")
            record = {"canary_id": "cn-" + secrets.token_hex(4), **item,
                      "session_id": session.session_id, "src": session.src, "planted_at": now}
            for value in lookup:
                _BY_VALUE[value] = record
            records.append(record)
        _BY_SESSION[session.session_id] = records
    return [dict(r) for r in records]


def check(username: str | None, password: str | None, src: str) -> dict | None:
    """Return an alert dict if the password (or username) is a planted canary value, else None."""
    with _LOCK:
        record, matched = None, None
        if password and password in _BY_VALUE:
            record, matched = _BY_VALUE[password], "password"
        elif username and username in _BY_VALUE:
            record, matched = _BY_VALUE[username], "username"
        if record is None:
            return None
        return {
            "canary_id": record["canary_id"],
            "kind": record["kind"],
            "path": record["path"],
            "planted_session": record["session_id"],
            "planted_src": record["src"],
            "planted_at": record["planted_at"],
            "reused_username": username,
            "reused_src": src,
            "matched": matched,
            "tags": list(REUSE_TAGS),
        }


def _reset() -> None:
    """Clear the registry (tests only)."""
    with _LOCK:
        _BY_VALUE.clear()
        _BY_SESSION.clear()
