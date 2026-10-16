"""Five seeded benchmark playbooks for CanaryNet multi-step consistency evaluation.

Each playbook contains at least 20 commands with explicit long-window persistence tests
where the fact query is separated from the fact creation by more than 10 intervening commands.
"""

from typing import Dict, List, NamedTuple


class LongWindowProbe(NamedTuple):
    write_step: int
    read_step: int
    path: str
    expected_content: str


PLAYBOOKS: Dict[str, List[str]] = {
    # Playbook 1: System Reconnaissance & Identity Invariance (22 commands)
    # Query distance: whoami at step 0 and 15 (> 10); hostname at step 1 and 21 (> 10)
    "playbook_1_recon": [
        "whoami",                          # 0
        "hostname",                        # 1
        "id",                              # 2
        "uname -a",                        # 3
        "pwd",                             # 4
        "cat /etc/os-release",             # 5
        "cat /etc/hostname",               # 6
        "cat /etc/passwd",                 # 7
        "uptime",                          # 8
        "ls /etc",                         # 9
        "ls -l /etc/passwd",               # 10
        "cat /etc/group",                  # 11
        "pwd",                             # 12
        "uname -m",                        # 13
        "id",                              # 14
        "whoami",                          # 15 (read back: 15 steps from step 0 > 10)
        "cat /etc/hostname",               # 16
        "ls /home/admin",                  # 17
        "cat /home/admin/.bashrc",         # 18
        "pwd",                             # 19
        "whoami",                          # 20
        "hostname",                        # 21 (read back: 20 steps from step 1 > 10)
    ],

    # Playbook 2: Long-Window File Lifecycle & Append/Recreation (24 commands)
    # Long window write at step 1, read at step 17 (16 intervening commands > 10 window)
    "playbook_2_file_lifecycle": [
        "cd /tmp",                         # 0
        "echo 'canary_token_99182' > token.txt",  # 1 (WRITE: target fact)
        "pwd",                             # 2
        "cd /home/admin",                  # 3
        "pwd",                             # 4
        "whoami",                          # 5
        "hostname",                        # 6
        "id",                              # 7
        "cat /etc/hostname",               # 8
        "mkdir /tmp/sandbox",              # 9
        "cd /tmp/sandbox",                 # 10
        "pwd",                             # 11
        "cd ..",                           # 12
        "pwd",                             # 13
        "whoami",                          # 14
        "ls /tmp",                         # 15
        "cd /tmp",                         # 16
        "cat token.txt",                   # 17 (READ: 16 steps after step 1; evicted from 10-cmd baseline)
        "echo 'appended_payload' >> token.txt",  # 18 (APPEND)
        "cat token.txt",                   # 19 (READ: verify append)
        "rm token.txt",                    # 20 (DELETE)
        "ls token.txt",                    # 21 (PROVE ABSENT)
        "echo 'reborn_token' > token.txt", # 22 (RECREATE)
        "cat token.txt",                   # 23 (READ: verify recreated content)
    ],

    # Playbook 3: Same-Basename Path Isolation (22 commands)
    # Writes config.json in /tmp and in /home/admin with distinct contents.
    # Reads both back after 11 intervening steps (> 10) to verify no cross-contamination.
    "playbook_3_same_basename": [
        "cd /tmp",                         # 0
        "echo 'tmp_config_alpha' > config.json",  # 1 (WRITE: /tmp/config.json)
        "pwd",                             # 2
        "cd /home/admin",                  # 3
        "echo 'home_config_beta' > config.json",  # 4 (WRITE: /home/admin/config.json)
        "pwd",                             # 5
        "whoami",                          # 6
        "hostname",                        # 7
        "id",                              # 8
        "cat /etc/os-release",             # 9
        "cat /etc/hostname",               # 10
        "ls /etc",                         # 11
        "uptime",                          # 12
        "pwd",                             # 13
        "whoami",                          # 14
        "id",                              # 15
        "cat /tmp/config.json",            # 16 (READ: /tmp/config.json, 15 steps after step 1 > 10)
        "cat /home/admin/config.json",     # 17 (READ: /home/admin/config.json, 13 steps after step 4 > 10)
        "rm /tmp/config.json",             # 18 (DELETE only /tmp/config.json)
        "cat /home/admin/config.json",     # 19 (READ: /home/admin/config.json must still exist!)
        "ls /tmp/config.json",             # 20 (PROVE: /tmp/config.json is absent)
        "pwd",                             # 21
    ],

    # Playbook 4: Deep Nested Navigation & Parent Directory Movement (22 commands)
    # Creates hierarchy, navigates down, writes nested file, traverses ../ back, reads relative path.
    "playbook_4_nested_navigation": [
        "cd /home/admin",                  # 0
        "pwd",                             # 1
        "mkdir workdir",                   # 2
        "cd workdir",                      # 3
        "pwd",                             # 4
        "mkdir subrepo",                   # 5
        "cd subrepo",                      # 6
        "pwd",                             # 7
        "echo 'deeply_nested_module' > module.py",  # 8 (WRITE)
        "cat module.py",                   # 9
        "cd ..",                           # 10
        "pwd",                             # 11
        "cat subrepo/module.py",           # 12
        "whoami",                          # 13
        "hostname",                        # 14
        "id",                              # 15
        "ls subrepo",                      # 16
        "cd ..",                           # 17 (traverses back to /home/admin)
        "pwd",                             # 18
        "cat workdir/subrepo/module.py",   # 19 (READ: read via relative path 11 steps after step 8 > 10)
        "ls workdir",                      # 20
        "pwd",                             # 21
    ],

    # Playbook 5: Exact Byte Size & Preserved Whitespace (22 commands)
    # Tests exact byte length consistency between cat and ls -l with zero tolerance, across > 10 steps.
    "playbook_5_exact_byte_size": [
        "cd /tmp",                         # 0
        "echo 'data_block_48_bytes_total_length_verification_ok' > metric.txt",  # 1 (WRITE: 49 bytes with newline)
        "cat metric.txt",                  # 2
        "ls -l metric.txt",                # 3
        "pwd",                             # 4
        "cd /home/admin",                  # 5
        "pwd",                             # 6
        "whoami",                          # 7
        "hostname",                        # 8
        "id",                              # 9
        "cat /etc/hostname",               # 10
        "cat /etc/os-release",             # 11
        "uptime",                          # 12
        "ls /etc",                         # 13
        "whoami",                          # 14
        "pwd",                             # 15
        "cat /tmp/metric.txt",             # 16 (READ: 15 steps after step 1 > 10)
        "ls -l /tmp/metric.txt",           # 17 (EXACT SIZE MATCH: zero tolerance)
        "cd /tmp",                         # 18
        "pwd",                             # 19
        "cat metric.txt",                  # 20
        "ls -l metric.txt",                # 21
    ],
}

# Explicit definition of the long-window fact verification probes
PROBES: List[LongWindowProbe] = [
    LongWindowProbe(
        write_step=1,
        read_step=17,
        path="/tmp/token.txt",
        expected_content="canary_token_99182\n",
    ),
    LongWindowProbe(
        write_step=1,
        read_step=16,
        path="/tmp/config.json",
        expected_content="tmp_config_alpha\n",
    ),
    LongWindowProbe(
        write_step=4,
        read_step=17,
        path="/home/admin/config.json",
        expected_content="home_config_beta\n",
    ),
    LongWindowProbe(
        write_step=8,
        read_step=19,
        path="/home/admin/workdir/subrepo/module.py",
        expected_content="deeply_nested_module\n",
    ),
    LongWindowProbe(
        write_step=1,
        read_step=16,
        path="/tmp/metric.txt",
        expected_content="data_block_48_bytes_total_length_verification_ok\n",
    ),
]
