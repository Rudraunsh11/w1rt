# AGENTS.md — rules for every human and AI agent in this repo

CanaryNet Lite: a decoy SSH host for a private lab. Ordinary commands are answered by
Python code from a session state; only unknown commands go to a small local model
(Ollama, Qwen2.5 1.5B), and every model reply is validated before state changes.

## Safety (never break; every review checks these)
1. Bind to `127.0.0.1` only. Never `0.0.0.0`, never a public interface.
2. Never execute visitor input. No `subprocess`, `os.system`, `os.popen`, `eval` or `exec`
   anywhere in the repo. `tests/test_safety.py` enforces this.
3. The only allowed outbound network call is loopback Ollama at `127.0.0.1:11434`.
4. No real credentials anywhere. Canary tokens are generated fake values only.
5. No code copied from GPL projects (for example Beelzebub, Cowrie). Write it yourself.
6. Check the licence of every new dependency and record it in `docs/decisions/`.
   Prefer the standard library.

## Contract
Exact names live in `contracts/README.md`. Never rename them. Change them only by
agreement of all three teammates, recorded in `docs/decisions/`.

## Code
- Python 3.11 or newer, standard library first. No paid APIs.
- Each module ships pytest tests in `tests/`. Run `pytest` from the repo root.
- Keep it small; the laptop is weak (no VMs, no Docker required).

## Git
- One branch per ticket, PR into `main`. Say "PR ready: <branch>" in chat.
- Exception: `canarynet/state/session.py` goes straight to `main` so others can import it.
- Do not add AI co-author trailers (`Co-Authored-By: ...`) or "Generated with ..." lines
  to commits or PRs. Commits are authored by the human who pushes them.

## Review checklist (lead merges within 10 minutes or gives a one-line reason)
- Contract names unchanged.
- `pytest` passes.
- No `subprocess` / `os.system` / `eval` / `exec`.
- No non-loopback network.
- No real credentials.
- No copied GPL code.

## Honest claims only
- Benchmark = measured multi-step consistency vs a "last 10 commands" baseline.
  Never call it a Cowrie test.
- "Local and free" is not unique (Cowrie's LLM backend and LLMHoney support Ollama).
- ATT&CK tags are rule-based. The injection guard is basic and has a test set.

## Schedule (IST, today)
Code freeze 14:30, submit by 15:05. Nothing big starts after 13:45.
