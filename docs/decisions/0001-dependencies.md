# 0001 — Dependencies and licences

Rule: standard library first. Every new dependency is added here with its licence
before its PR is merged. No GPL code is copied into the repo.

| Package | Used for | Licence | Status |
|---|---|---|---|
| pytest | tests | MIT | accepted |
| (stdlib) `urllib.request` | loopback call to Ollama `127.0.0.1:11434` | PSF | proposed, avoids a client library |
| asyncssh *or* paramiko | SSH front (Aayush picks) | asyncssh: EPL-2.0 with GPL-2.0+ secondary — VERIFY; paramiko: LGPL-2.1 — VERIFY | open |

Using a library as an installed dependency is not copying its code. Copying code
from GPL projects (for example Beelzebub, Cowrie) is not allowed.
