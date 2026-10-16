# 0001 — Dependencies and licences

Rule: standard library first. Every new dependency is added here with its licence
before its PR is merged. No GPL code is copied into the repo.

Licences below were read from the installed package metadata (`importlib.metadata`,
License-Expression field) on 2026-10-16.

| Package | Version checked | Used for | Licence |
|---|---|---|---|
| pytest | 8.x | tests | MIT |
| httpx | 0.28.1 | loopback call to Ollama `127.0.0.1:11434` | BSD-3-Clause |
| asyncssh | 2.24.1 | SSH front | EPL-2.0 OR GPL-2.0-or-later (we use it under EPL-2.0) |

Pulled in by the above (all permissive):

| Package | Version | Licence |
|---|---|---|
| httpcore | 1.0.9 | BSD-3-Clause |
| anyio | 4.14.2 | MIT |
| h11 | 0.16.0 | MIT |
| idna | 3.19 | BSD-3-Clause |
| certifi | 2026.7.22 | MPL-2.0 |
| cryptography | 50.0.0 | Apache-2.0 OR BSD-3-Clause |
| cffi | 2.1.1 | MIT-0 |
| pycparser | 3.0 | BSD-3-Clause |
| typing_extensions | 4.16.0 | PSF-2.0 |

Using a library as an installed dependency is not copying its code. Copying code
from GPL projects (for example Beelzebub, Cowrie) is not allowed.
