"""Conservative command-text heuristics, never proof of successful compromise.

Technique names/IDs checked against MITRE's enterprise-attack-20.0.json.
This module uses no network and never executes or evaluates command text.
"""

import posixpath
import re
import shlex


ATTACK_VERSION = "20.0"
ATTACK_SOURCE = "MITRE enterprise-attack-20.0.json; evidence in LICENSE_AUDIT.md"
TECHNIQUES = {
    "T1082": "System Information Discovery",
    "T1083": "File and Directory Discovery",
    "T1033": "System Owner/User Discovery",
    "T1057": "Process Discovery",
    "T1087.001": "Account Discovery: Local Account",
    "T1016": "System Network Configuration Discovery",
    "T1049": "System Network Connections Discovery",
    "T1105": "Ingress Tool Transfer",
    "T1552.001": "Unsecured Credentials: Credentials In Files",
    "T1098.004": "Account Manipulation: SSH Authorized Keys",
    "T1053.003": "Scheduled Task/Job: Cron",
    "T1136.001": "Create Account: Local Account",
    "T1070.003": "Indicator Removal: Clear Command History",
    "T1548.003": "Abuse Elevation Control Mechanism: Sudo and Sudo Caching",
    "T1496.001": "Resource Hijacking: Compute Hijacking",
    "T1059.004": "Command and Scripting Interpreter: Unix Shell",
}
VERIFICATION = {technique: "verified in ATT&CK v20.0" for technique in TECHNIQUES}

COMMAND_RULES = {
    "uname": "T1082", "hostname": "T1082",
    "ls": "T1083", "find": "T1083",
    "whoami": "T1033", "id": "T1033",
    "ps": "T1057", "ifconfig": "T1016",
    "netstat": "T1049", "ss": "T1049",
    "wget": "T1105", "curl": "T1105",
    "crontab": "T1053.003", "useradd": "T1136.001",
    "sudo": "T1548.003",
    "sh": "T1059.004", "bash": "T1059.004", "dash": "T1059.004",
    "zsh": "T1059.004", "ksh": "T1059.004",
}
_READERS = {"cat", "less", "more", "head", "tail", "grep", "sed", "awk"}
_EDITORS = {"vi", "vim", "nano", "tee", "touch", "cp", "mv", "install"}
_MINER = re.compile(r"(?:^|[/_.-])(xmrig|cpuminer|cryptominer|miner)(?:$|[/_.-])", re.I)
_SEPARATORS = {";", "&&", "||", "|", "&", "(", ")"}


def _tokens(line):
    # Non-POSIX mode retains quotes around standalone operators: echo ">"
    # must not be treated as a write to the following path.
    lexer = shlex.shlex(line, posix=False, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    lexer.commenters = "#"
    return list(lexer)


def _word(token):
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _segment_tags(raw):
    words = [_word(token) for token in raw]
    if not words:
        return set()
    command = posixpath.basename(words[0])
    args = words[1:]
    tags = {COMMAND_RULES[command]} if command in COMMAND_RULES else set()
    if command == "ip" and args and args[0] in {"a", "addr", "address"}:
        tags.add("T1016")
    if command in _READERS:
        paths = [posixpath.normpath(arg) for arg in args if not arg.startswith("-")]
        if "/etc/passwd" in paths:
            tags.add("T1087.001")
        if any(posixpath.basename(path) == ".env" for path in paths):
            tags.add("T1552.001")
    # Reads of authorized_keys alone are not edits. Redirection operators
    # must be unquoted, and editor targets must have the exact basename.
    for i, token in enumerate(raw[:-1]):
        if token in {">", ">>"}:
            target = posixpath.basename(words[i + 1])
            if target == "authorized_keys":
                tags.add("T1098.004")
            if target in {".bash_history", ".zsh_history"}:
                tags.add("T1070.003")
    if command in _EDITORS and args and posixpath.basename(args[-1]) == "authorized_keys":
        tags.add("T1098.004")
    if command == "history" and "-c" in args:
        tags.add("T1070.003")
    if command in {"rm", "truncate"} and any(
        posixpath.basename(arg) in {".bash_history", ".zsh_history"} for arg in args
    ):
        tags.add("T1070.003")
    if _MINER.search(words[0]) or (
        command in {"wget", "curl"} and any(_MINER.search(arg) for arg in args)
    ):
        tags.add("T1496.001")
    if command == "sudo":
        # Only unwrap simple sudo flags; options taking values are deliberately
        # left unsupported rather than guessing which argument is a command.
        offset = 0
        while offset < len(args) and args[offset] in {"-n", "-E", "-H", "--"}:
            offset += 1
        if offset < len(args) and not args[offset].startswith("-"):
            tags |= _segment_tags(raw[offset + 1:])
    return tags


def tag(line):
    """Return sorted, unique technique IDs for supported command patterns.

    This intentionally covers a small shell subset. It does not expand aliases,
    substitutions or variables, infer login events, or infer successful attacks.
    """
    if not isinstance(line, str) or not line.strip():
        return []
    try:
        tokens = _tokens(line)
    except ValueError:
        return []
    tags = set()
    segment = []
    for token in tokens + [";"]:
        if token in _SEPARATORS:
            tags |= _segment_tags(segment)
            segment = []
        else:
            segment.append(token)
    return sorted(tags)

