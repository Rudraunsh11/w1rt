# Live walkthrough script (3 minutes)

This is the script to follow, **not a record of a completed run**. It needs PR #2
(SSH front, model adapter) and PR #10 (canaries in SSH sessions) merged on `main`.
Step 1:55 (canary login) is cut in this release; skip it.

Setup before the walkthrough:
- Ollama running on `127.0.0.1:11434` with `qwen2.5:1.5b`; send one warm-up prompt
  (`ollama run qwen2.5:1.5b "say ok"`) so the first model answer is not a cold start.
- `git pull` on `main`, `python -m pytest -q` green.
- Windows Terminal, two panes, large font. Close notifications.
- Left pane: `python -m canarynet --port 2222`. It must print **no** stand-in warning.
- Right pane: ready to type `ssh -p 2222 admin@127.0.0.1` (password `admin`).

Rules during the walkthrough: one command per line; no `|`, `;` or `&&` (those go to the
model as a whole line); if the model is slow, keep talking, do not retype.

| Time | Type | Say |
|---|---|---|
| 0:00 | (title, both panes visible) | "CanaryNet Lite is a decoy Linux server for a private lab. It answers like a real host, remembers what it showed, plants fake credentials and tags what visitors try with MITRE ATT&CK." |
| 0:15 | `ssh -p 2222 admin@127.0.0.1` | "It only listens on 127.0.0.1, and nothing a visitor types is ever executed." |
| 0:25 | `whoami` · `hostname` · `cat /etc/os-release` | "Ordinary commands are answered instantly by Python code from the session state, so facts never change." |
| 0:45 | `mkdir loot` · `cd loot` · `echo stolen > data.txt` · `cat data.txt` · `pwd` · `ls` | "The state is owned by code: the file we wrote is still there, and `pwd` agrees with `cd`." |
| 1:15 | `systemctl status nginx` | "Unknown commands go to a small local model, Qwen 2.5 1.5B on Ollama. Its reply is validated before anything in the state changes." |
| 1:40 | `cat /var/www/html/.env` | "Each session gets its own fake credentials: a canary. They are random per visitor, so reuse points back to this session." |
| 1:55 | _only if the canary login shipped:_ `exit`, then `ssh -p 2222 webapp@127.0.0.1` with that password | "Reusing the leaked password fires a canary alert tagged T1552.001 and T1078." |
| 2:10 | `exit`, then in the left pane `python -m canarynet.report` and open `report.html` | "Every command is logged with who answered it, the latency and rule-based ATT&CK tags." |
| 2:30 | README results table | "We measured multi-step consistency against a baseline that only remembers the last 10 commands, same model. Here are the numbers." (read pass rate and contradictions per 100 for both) |
| 2:50 | README "Honest limits" | "Limits: lab only, 14 commands in code, a basic injection guard, and local-and-free is not unique. Thank you." |

If something breaks, say so and show the failure; do not hide it.
