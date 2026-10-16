# Security

## What this is
CanaryNet Lite is a research decoy for a **private lab**. It is not hardened for
the public internet. Do not expose it outside your own machine.

## Design guarantees
- Listens on `127.0.0.1` only.
- Visitor input is never executed. The shell is simulated in Python from a session
  state; there is no `subprocess`, `os.system`, `eval` or `exec` in the code
  (checked by `tests/test_safety.py`).
- The only outbound call is to a local Ollama server on `127.0.0.1:11434`.
- Model replies are validated against a fixed schema before any state change.
- All "credentials" shown to visitors are fake canary tokens generated per session.

## Logs
Logs may contain whatever a visitor typed. They stay local in `logs/` (git-ignored).
Do not commit them.

## Reporting a problem
Open a GitHub issue without exploit details, or contact a maintainer directly.
