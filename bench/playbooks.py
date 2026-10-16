"""Five seeded benchmark playbooks for CanaryNet consistency evaluation."""

from typing import Dict, List

PLAYBOOKS: Dict[str, List[str]] = {
    # Playbook 1: System Identification and Baseline Reconnaissance (10 commands)
    "playbook_1_recon": [
        "whoami",
        "hostname",
        "id",
        "uname -a",
        "pwd",
        "cat /etc/os-release",
        "uptime",
        "ls",
        "whoami",
        "hostname",
    ],

    # Playbook 2: File Lifecycle & Content Integrity (10 commands)
    "playbook_2_file_lifecycle": [
        "pwd",
        "cd /tmp",
        "pwd",
        "echo 'hello canary 123' > note.txt",
        "cat note.txt",
        "ls note.txt",
        "ls -l note.txt",
        "cat note.txt",
        "rm note.txt",
        "ls note.txt",
    ],

    # Playbook 3: Directory Traversal and Nested File Mutations (10 commands)
    "playbook_3_directory_tree": [
        "cd /home/admin",
        "pwd",
        "mkdir workdir",
        "cd workdir",
        "pwd",
        "echo 'project payload' > payload.sh",
        "cat payload.sh",
        "cd ..",
        "pwd",
        "ls workdir",
    ],

    # Playbook 4: Command Idempotence and Repeated State Queries (10 commands)
    "playbook_4_idempotence": [
        "whoami",
        "whoami",
        "hostname",
        "hostname",
        "echo 'alpha data' > /tmp/idempotent.txt",
        "cat /tmp/idempotent.txt",
        "cat /tmp/idempotent.txt",
        "rm /tmp/idempotent.txt",
        "ls /tmp/idempotent.txt",
        "cat /tmp/idempotent.txt",
    ],

    # Playbook 5: Environment & Context Persistence (10 commands)
    "playbook_5_env_persistence": [
        "whoami",
        "id",
        "export HACK_VAR=canary_active",
        "echo $HACK_VAR",
        "cd /var",
        "pwd",
        "cd /home/admin",
        "pwd",
        "whoami",
        "hostname",
    ],
}
