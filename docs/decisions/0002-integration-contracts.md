# 0002 — Integrate Rudraunsh's modules with the production router

- Preserve the original `canarynet.logger.log_event` contract path. The router,
  integration checks and contract reference now import that path; the earlier
  `canarynet.attack.logger` reference was a wiring error, not a renamed API.
- Preserve Result.stdout bytes. The router must not add a newline to `echo -n`,
  `cat`, model output or redirected content. Code-generated error messages still
  terminate with a newline. File byte sizes and readback can now agree exactly.
- Runtime handlers stay standard-library only and use production Session methods.
  The test-only stand-in is retained for isolated handoff, but is unused when
  Session is installed. No process-launch API is used in repository code/tests.
- JSONL locking uses `fcntl` on POSIX and `msvcrt` on Windows, with a stable lock
  file byte. POSIX thread/process tests and a Windows API-shape test pass here;
  an actual Windows runtime run is VERIFY on Aayush's machine.
- ATT&CK source links live in the documentation; runtime rules do not initiate
  network requests. Rule tests use loopback-shaped fixture strings only.

Public class, function, path and argument names are unchanged. No live model
results are claimed. SSH and benchmark integration wait for Aayush's repaired PR.
