# Submission checklist

Code freeze **14:30 IST**, submit by **15:05 IST** (2026-10-16).

## 1. Code on main
- [ ] All open PRs merged or closed; `git switch main && git pull`.
- [ ] `python -m pytest -q` passes.
- [ ] `python -m canarynet` starts with **no** stand-in warning.

## 2. Final safety grep (run on main)
```sh
git grep -nE "subprocess|os\.system|os\.popen|\beval\(|\bexec\(" -- "*.py"
git grep -n "0\.0\.0\.0" -- "*.py"
git grep -nE "https?://" -- "*.py"
git grep -nE "AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY"
git ls-files | grep -iE "host_key|\.key$|\.pem$|events\.jsonl|\.env$"
```
Expected: the first two only match `tests/test_safety.py` (its own patterns); the URL
grep only shows `127.0.0.1` addresses; the last two print nothing.

## 3. Results in the README
- [ ] Fill the table from `bench/results_ours.json` and `bench/results_baseline.json`:
      `pass_rate_pct`, `contradictions_per_100`, `share_answered_by_code`,
      `median_latency_ms`, `total_commands`, and `host_metadata` for hardware.
- [ ] Write the commit hash the benchmark ran on.
- [ ] Both JSON files committed.

## 4. Honest claims pass
- [ ] Nowhere says "Cowrie test" or that local/free inference is unique.
- [ ] "Honest limits" still true (canary login: shipped or cut?).
- [ ] No VERIFY left that a judge would read as a claim; remove or keep it marked.

## 5. Release
- [ ] Tag the release on main, for example `git tag -a v1.0 -m "Hackathon submission"` then `git push origin v1.0`.
- [ ] Repository is public; LICENSE (Apache-2.0) and LICENSE_AUDIT.md present.

## 6. Submit (by 15:05)
- [ ] Repo URL, short description, team names in the submission form (no demo video).
