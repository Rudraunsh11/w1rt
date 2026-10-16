"""Append decoy events to JSONL, never interpreting visitor input."""

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows; both locking implementations are stdlib.
    fcntl = None
    import msvcrt


_WRITE_LOCK = threading.Lock()


def _lock(stream):
    stream.seek(0)
    if fcntl is not None:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
    else:
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)


def _unlock(stream):
    stream.seek(0)
    if fcntl is not None:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    else:
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def log_event(session_id, src, input, output, answered_by, latency_ms, tags):
    """Append one event to logs/events.jsonl relative to the working directory.

    A thread lock and platform file lock protect concurrent callers, including
    separate processes sharing this local file. I/O errors propagate to the
    caller rather than silently discarding an event. Callers supply synthetic
    lab data only; this function preserves the seven contract fields.
    """
    event = {
        "session_id": session_id,
        "src": src,
        "input": input,
        "output": output,
        "answered_by": answered_by,
        "latency_ms": latency_ms,
        "tags": tags,
    }
    # Serialize before opening the file so invalid values cannot leave a
    # partially written JSON record. Embedded newlines are escaped by JSON.
    json.dumps(event, ensure_ascii=False, allow_nan=False)
    path = Path("logs/events.jsonl")
    with _WRITE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        # A separate, nonempty lock file gives Windows a stable byte range.
        # It also protects the initial creation of the append-only event log.
        with (path.parent / ".events.lock").open("a+b") as guard:
            guard.seek(0, 2)
            if guard.tell() == 0:
                guard.write(b"\0")
                guard.flush()
            _lock(guard)
            try:
                event["timestamp"] = datetime.now(timezone.utc).isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z")
                line = json.dumps(event, ensure_ascii=False, allow_nan=False)
                with path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(line + "\n")
                    stream.flush()
            finally:
                _unlock(guard)

