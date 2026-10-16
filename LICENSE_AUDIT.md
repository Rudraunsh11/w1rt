# Licence audit — October 16, 2026

This is an evidence inventory, not a claim that the unfinished team distribution
is cleared. Only Rudraunsh's standard-library modules and test dependencies have
been exercised here. No third-party source or model weights are vendored in this
repository. Retain upstream copyright/licence/NOTICE files when distributing
dependencies or weights. Exact team versions, binaries and transitives remain
VERIFY until Aayush supplies the resolved environment.

## Local runtime and test environment

The installed distributions' METADATA and licence files were read from the test
virtual environment's `lib/python3.14/site-packages/*.dist-info/licenses/`.
The package licence summaries below were checked against those files.

| Component | Version checked | Licence | Evidence / status |
|---|---|---|---|
| Python / standard library | 3.12.14, 3.14.6 runtimes | PSF licence and bundled notices | [Python licence](https://docs.python.org/3.11/license.html); exact binary bundled notices VERIFY |
| pytest | 9.1.1 | MIT | Installed `pytest-9.1.1.dist-info/licenses/LICENSE`; [upstream](https://docs.pytest.org/en/stable/license.html) |
| iniconfig | 2.3.1 | MIT | Installed `iniconfig-2.3.1.dist-info/licenses/LICENSE` |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | Installed `packaging-26.3.dist-info/licenses/LICENSE`, `LICENSE.APACHE`, `LICENSE.BSD` |
| pluggy | 1.7.0 | MIT | Installed `pluggy-1.7.0.dist-info/licenses/LICENSE` |
| Pygments | 2.21.0 | BSD-2-Clause | Installed `pygments-2.21.0.dist-info/licenses/LICENSE` |
| pip (setup tool only) | 26.1.2 | MIT; vendor notices separate | Installed metadata; full vendor-notice audit VERIFY; not shipped with application source |

## Team runtime, model and developer tools

| Component | Licence / source | Status and required follow-up |
|---|---|---|
| CanaryNet application | Apache-2.0 intended by team | Verified: Apache-2.0 LICENSE is present on integrated main |
| AsyncSSH | EPL-2.0 OR GPL-2.0-or-later, [maintainer package page](https://pypi.org/project/asyncssh/) | Upstream dual licence verified; use EPL-2.0 route. Installed version/notices VERIFY; no source copied |
| Requests | Apache-2.0, [upstream LICENSE](https://raw.githubusercontent.com/psf/requests/main/LICENSE) | Upstream verified; actual installed version/notices VERIFY |
| AsyncSSH/Requests transitives | **VERIFY** exact resolved set and licence files | Resolve on Aayush's Python/OS; include cryptography, typing_extensions, cffi/pycparser if selected, charset-normalizer, idna, urllib3 and certifi if selected; do not treat this candidate list as a completed audit |
| Ollama server | MIT, [upstream LICENSE](https://raw.githubusercontent.com/ollama/ollama/main/LICENSE) | Upstream verified; installed version, bundled inference libraries and notices VERIFY |
| Qwen2.5-1.5B-Instruct weights | Apache-2.0, [publisher LICENSE](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/blob/main/LICENSE) | Publisher licence verified for this exact model; selected Ollama tag/digest and correspondence to these weights VERIFY |
| Git (developer tool) | GPL-2.0, [COPYING](https://raw.githubusercontent.com/git/git/master/COPYING) | Tool version 2.53.0 observed. No Git source copied or redistributed with the application |
| Codex CLI (developer tool) | Apache-2.0 source, [upstream LICENSE](https://raw.githubusercontent.com/openai/codex/main/LICENSE) | Source licence verified; packaged CLI 0.163.0-alpha.10.2 distribution terms/notices VERIFY; account services separate |
| Claude (Snehank's developer tool) | **VERIFY** service terms for his product/account | No code or dependency bundled from this service; team must identify exact product/terms |
| Antigravity (Aayush's developer tool) | **VERIFY** product licence/terms | Team must identify exact version and official terms |
| MITRE ATT&CK v20.0 references | [MITRE legal/branding terms](https://attack.mitre.org/resources/legal-and-branding/) | IDs/names verified in versioned dataset; exact reference-data redistribution terms/notices VERIFY; do not imply MITRE endorsement |

Do not install aiohttp, Streamlit, GPU packages or a paid model API for
Rudraunsh's modules. Test dependencies listed above are not runtime imports.
The final audit must use the actual lockfile/environment, not the latest
available package version as a substitute. A dry-run resolver snapshot, when
available, identifies candidates only and does not establish Aayush's environment.

## Resolver candidates (not the final installed environment)

A pip dry-run for `asyncssh requests` on this Mac/Python 3.14 resolved the
following on October 16. Licence expressions were read from maintainer-published
wheel metadata from PyPI. Exact licence files, compiled/bundled dependencies,
notice obligations and the final benchmark environment still require **VERIFY**.
No runtime packages were installed by this dry-run.

| Candidate | Version | Maintainer metadata licence | Primary metadata source |
|---|---|---|---|
| asyncssh | 2.24.1 | EPL-2.0 OR GPL-2.0-or-later | [PyPI](https://pypi.org/project/asyncssh/2.24.1/) |
| requests | 2.34.2 | Apache-2.0 | [PyPI](https://pypi.org/project/requests/2.34.2/) |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | [PyPI](https://pypi.org/project/cryptography/50.0.2/) |
| typing_extensions | 4.16.0 | PSF-2.0 | [PyPI](https://pypi.org/project/typing-extensions/4.16.0/) |
| cffi | 2.1.1 | MIT-0 | [PyPI](https://pypi.org/project/cffi/2.1.1/) |
| pycparser | 3.11 | BSD-3-Clause | [PyPI](https://pypi.org/project/pycparser/3.11/) |
| charset-normalizer | 3.5.2 | MIT | [PyPI](https://pypi.org/project/charset-normalizer/3.5.2/) |
| idna | 3.20 | BSD-3-Clause | [PyPI](https://pypi.org/project/idna/3.20/) |
| urllib3 | 2.8.0 | MIT | [PyPI](https://pypi.org/project/urllib3/2.8.0/) |
| certifi | 2026.7.22 | MPL-2.0 | [PyPI](https://pypi.org/project/certifi/2026.7.22/) |

## Integrated environment verified locally

The current declared stack after Snehank PR #4 uses httpx and asyncssh; Requests is no longer a runtime requirement. These actual installed versions supersede candidate dry-run versions above. Metadata and the wheel-provided licence files were read locally. Binary bundled notices and the exact benchmark host environment remain VERIFY.

| Package | Installed version | Licence expression | Evidence |
|---|---|---|---|
| httpx | 0.28.1 | BSD-3-Clause | Installed metadata + 1 licence/notice file(s) read |
| asyncssh | 2.24.1 | EPL-2.0 OR GPL-2.0-or-later | Installed metadata + 1 licence/notice file(s) read |
| httpcore | 1.0.9 | BSD-3-Clause | Installed metadata + 1 licence/notice file(s) read |
| anyio | 4.15.1 | MIT | Installed metadata + 1 licence/notice file(s) read |
| h11 | 0.16.0 | MIT | Installed metadata + 1 licence/notice file(s) read |
| idna | 3.20 | BSD-3-Clause | Installed metadata + 1 licence/notice file(s) read |
| certifi | 2026.7.22 | MPL-2.0 | Installed metadata + 1 licence/notice file(s) read |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | Installed metadata + 3 licence/notice file(s) read |
| cffi | 2.1.1 | MIT-0 | Installed metadata + 1 licence/notice file(s) read |
| pycparser | 3.11 | BSD-3-Clause | Installed metadata + 1 licence/notice file(s) read |
| typing_extensions | 4.16.0 | PSF-2.0 | Installed metadata + 1 licence/notice file(s) read |
| pytest | 9.1.1 | MIT | Installed metadata + 1 licence/notice file(s) read |
| iniconfig | 2.3.1 | MIT | Installed metadata + 1 licence/notice file(s) read |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | Installed metadata + 3 licence/notice file(s) read |
| pluggy | 1.7.0 | MIT | Installed metadata + 1 licence/notice file(s) read |
| Pygments | 2.21.0 | BSD-2-Clause | Installed metadata + 2 licence/notice file(s) read |
