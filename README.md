# CanaryNet Lite

A decoy computer for a private lab: a fake SSH server that answers like a Linux host,
remembers what it showed, plants fake credentials (canaries), and logs what visitors
try with MITRE ATT&CK tags.

- Ordinary commands are answered by Python code from a session state.
- Only unknown commands go to a small local model (Ollama, Qwen2.5 1.5B).
- Every model reply is validated before the state changes.

> Status: under construction (hackathon build). Results table coming in v1.0.

## Safety
Loopback only (`127.0.0.1`), visitor input is never executed, no real credentials.
See [SECURITY.md](SECURITY.md).

## Quick start
_TBD (v0.1)._ Target: `ssh -p 2222 admin@127.0.0.1`

## Results
_TBD: consistency benchmark vs a "last 10 commands" baseline._

## Layout
```
canarynet/
  fronts/     SSH front end
  router/     command router + code handlers
  state/      session state (fake filesystem, env, history)
  llm/        Ollama adapter, reply validator, injection guard
  canary/     fake credential planting and reuse detection
  attack/     logging and rule-based ATT&CK tags
  dashboard/  local web view
bench/        benchmark playbooks, checkers, baseline mode
contracts/    shared interface names (do not rename)
docs/decisions/  short decision records
```

## Team
Snehank (lead), Aayush, Rudraunsh.

## Licence
Apache-2.0, see [LICENSE](LICENSE).
