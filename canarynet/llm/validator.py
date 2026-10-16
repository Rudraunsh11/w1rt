"""Reply validation gatekeeper for CanaryNet LLM output."""

from typing import Any, Dict, Optional
from canarynet.llm import guard
from canarynet.state.session import Result, Session

ALLOWED_OPS = {"create_file", "write_file", "delete_file", "chdir", "set_env"}
MAX_STDOUT_LEN = 2000
MAX_STATE_CHANGES = 5


def validate(reply: Any, session: Optional[Session] = None) -> Optional[Result]:
    """Validates model reply against contract schema and safety rules.

    Rejection criteria:
    - reply is not a dict
    - missing stdout, exit_code, or state_changes
    - stdout is not str or exceeds 2000 characters
    - exit_code is not int
    - state_changes is not a list or has more than 5 entries
    - unknown op in state_changes
    - filesystem paths not absolute or containing '..'
    - guard.check_output fails on stdout or content

    Returns:
        Result object if valid, else None.
    """
    if not isinstance(reply, dict):
        return None

    stdout = reply.get("stdout")
    exit_code = reply.get("exit_code")
    state_changes = reply.get("state_changes")

    if not isinstance(stdout, str) or len(stdout) > MAX_STDOUT_LEN:
        return None

    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        return None

    if not isinstance(state_changes, list) or len(state_changes) > MAX_STATE_CHANGES:
        return None

    # Guard check on model stdout
    if not guard.check_output(stdout):
        return None

    validated_changes = []
    for item in state_changes:
        if not isinstance(item, dict):
            return None

        op = item.get("op")
        path = item.get("path")
        content = item.get("content")

        if op not in ALLOWED_OPS:
            return None

        if not isinstance(path, str) or not path:
            return None

        # Path traversal check
        if ".." in path:
            return None

        if op == "set_env":
            # For set_env, path holds variable name and content holds value
            if not path.isidentifier() and not all(c.isalnum() or c == "_" for c in path):
                return None
            if content is not None and not isinstance(content, str):
                return None
        else:
            # Filesystem ops require absolute paths
            if not path.startswith("/"):
                return None
            if content is not None and not isinstance(content, str):
                return None

        # Guard check on any written file content
        if content and not guard.check_output(content):
            return None

        validated_changes.append(item)

    return Result(
        stdout=stdout,
        exit_code=exit_code,
        state_changes=validated_changes,
    )
