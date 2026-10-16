# CanaryNet Lite

A decoy computer for a private lab: a fake SSH server that answers like a Linux host,
remembers what it showed, plants fake credentials (canaries), and logs what visitors
try with MITRE ATT&CK tags.

- Ordinary commands are answered by Python code from a session state.
- Only unknown commands go to a small local model (Ollama, Qwen2.5 1.5B).
- Every model reply is validated before the state changes.

> Integration status: 160 tests pass, 3 skipped on macOS/Python 3.14.6.
> Production state/router, canary registry, 14 command handlers, JSONL logging and
> the HTML report work together. SSH/model/checker integration awaits Aayush's
> repaired PR #2; this is not yet a completed live-model demo.

## Safety
Loopback only (`127.0.0.1`), visitor input is never executed, no real credentials.
See [SECURITY.md](SECURITY.md). Only trusted loopback Ollama traffic at
`127.0.0.1:11434` is allowed. External-egress enforcement and CPU-only model
configuration remain VERIFY. A loopback server binding alone does not enforce egress.

## Quick start
Python 3.11+ source target; an actual 3.11/Windows run remains VERIFY.

```sh
git clone https://github.com/Rudraunsh11/w1rt.git
cd w1rt
git switch feat/integration-contracts
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
python -m canarynet.report
```

The integration branch must be published before remote checkout is available.
On Windows activate with `.venv\Scripts\activate`. On macOS, if Git is missing,
run `xcode-select --install` in Terminal and complete installation first.

The report writes `report.html` from `logs/events.jsonl`; open the file in a
browser (`open report.html` on macOS). An absent log produces an explanatory empty
report. Valid events are grouped by session and ordered in UTC; malformed lines
are skipped and counted. Visitor text is escaped and no external assets are used.

Once SSH merges, start with `python -m canarynet --port 2222`, then connect only
to `ssh -p 2222 admin@127.0.0.1` using synthetic credentials. The CLI has no host
option. It currently cannot start because the SSH front is not merged.

Rudraunsh's runtime modules are standard-library only: JSON/time/HTML utilities
format events and reports, POSIX path/shlex/regex utilities inspect simulated
paths and text, and threading/platform locks protect writes. `pytest` runs tests;
the declared team packages `httpx` and `asyncssh` provide loopback HTTP and SSH.
The logger uses `fcntl` on POSIX and `msvcrt` on Windows. POSIX process/thread
tests pass; the Windows API is checked with a double, not a real Windows run.

### Commands and contract

`ls` (-l/-a), `cd`, `pwd`, `cat`, `whoami`, `id`, `uname` (-a), `hostname`,
`echo` (-n), `mkdir` (-p), `touch`, `rm` (-f, files only), `ps` (synthetic) and
`history` (read-only, optional count). Only one ls path is supported.

Handlers receive `(session, argv)` without the command name, mutate through
Session methods and return empty state_changes. The router handles `>`/`>>`,
history and model proposals once. `echo` only prints. Stdout/file bytes are
preserved, including missing final newlines. The original `canarynet.logger`
import path is used; no public CONTRACT name changed.

`log_event(session_id, src, input, output, answered_by, latency_ms, tags)` adds a
UTC timestamp and appends one UTF-8 JSON line. A stable `.events.lock` protects
concurrent writers; I/O failures propagate. Rotation, tamper-proofing and network
filesystem guarantees are outside this MVP.

Persona: admin, uid/gid 1000, groups admin/sudo, `/home/admin`, `web-prod-01`.
The requested uname text remains `Linux web-prod-01 5.15.0-91-generic #101-Ubuntu
SMP x86_64 GNU/Linux`. Its real Ubuntu build correspondence is VERIFY. Snehank's
KERNEL constant is currently `5.15.0-58-generic`; align it and the SSH banner before
claiming every host fact agrees. File dates/permissions and ps entries are synthetic.

## Results
The comparison is a **last-10-command baseline**, never a Cowrie test. Snehank's
real baseline helper is merged, but the runner/checkers still need repair and
integration. Run these only after the repaired benchmark package arrives:

```sh
python -m bench.run --mode ours
python -m bench.run --mode baseline
```

| Measurement | Ours | Last-10-command baseline |
|---|---|---|
| Applicable assertions passed / evaluated | VERIFY — not run | VERIFY — not run |
| Median / p95 latency | VERIFY — not run | VERIFY — not run |
| Model calls / timeouts / rejected replies | VERIFY — not run | VERIFY — not run |
| Guard pass count / total | VERIFY — not integrated | VERIFY — applicability |

Use five long-context playbooks and six meaningful checkers, identical model/
decoding settings, raw traces and actual hardware metadata. An empty or irrelevant
trace must not score 100%. Planned model is Qwen2.5 1.5B; tag/digest, quantization,
settings and warm-up policy remain VERIFY. Aayush's benchmark laptop is reported
as 12 GB RAM, CPU-only; final metadata is VERIFY. Development here used macOS
26.2, Apple M4, 24 GB RAM. Unit tests are not live-model benchmark results.

Sixteen command IDs/names were verified against [Enterprise ATT&CK v20.0](https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack-20.0.json).
Rules inspect command position and selected arguments, not aliases or expansions;
`echo uname` does not imply discovery. Frontends supply login/canary tags separately.
Labels describe **attempts/rule matches, not proven success**. No automatic T1190
on generic web probing. Local/free inference is not unique; the guard is basic.

## Layout
```
canarynet/
  fronts/     SSH front end
  router/     command router + code handlers
  state/      session state (fake filesystem, env, history)
  llm/        Ollama adapter, reply validator, injection guard
  canary/     fake credential planting and reuse detection
  attack/     rule-based ATT&CK tags
  logger.py   concurrent JSONL event log
  report.py   self-contained escaped HTML report
bench/        benchmark playbooks, checkers, baseline mode
contracts/    shared interface names (do not rename)
docs/decisions/  short decision records
```

## Team
Snehank (lead), Aayush, Rudraunsh.

## Licence
Apache-2.0, see [LICENSE](LICENSE).

See [LICENSE_AUDIT.md](LICENSE_AUDIT.md) and `docs/decisions/0001-dependencies.md`
for actual installed package versions and licence evidence. Exact benchmark-host
versions, model digest and binary bundled notices remain VERIFY. No GPL project
source is copied; retain required notices when distributing dependencies/weights.

Freeze **14:30 IST**, submit **15:05 IST**, October 16, 2026. Before release:
wire canaries into SSH, integrate model/guard, align host facts, rerun tests and
replace benchmark placeholders with measured results. Optional web waits until
preceding work is merged and green. Preserve state, evidence, safety, logging/
report, LICENSE and README when cutting scope.
