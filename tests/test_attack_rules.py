import pytest

from canarynet.attack.rules import ATTACK_VERSION, TECHNIQUES, VERIFICATION, tag


@pytest.mark.parametrize("line,expected", [
    ("uname -a", ["T1082"]), ("hostname", ["T1082"]),
    ("ls -la /etc", ["T1083"]), ("find /home -name .env", ["T1083"]),
    ("whoami", ["T1033"]), ("/usr/bin/id", ["T1033"]),
    ("ps aux", ["T1057"]), ("cat /etc/passwd", ["T1087.001"]),
    ("head /etc/../etc/passwd", ["T1087.001"]),
    ("ip a", ["T1016"]), ("ip addr show", ["T1016"]),
    ("ifconfig", ["T1016"]), ("netstat -an", ["T1049"]), ("ss -tulpn", ["T1049"]),
    ("curl http://127.0.0.1:11434/file", ["T1105"]),
    ("wget http://127.0.0.1:11434/file", ["T1105"]),
    ("cat /home/admin/.env", ["T1552.001"]), ("cat '.env'", ["T1552.001"]),
    ("echo fake > /home/admin/.ssh/authorized_keys", ["T1098.004"]),
    ("echo fake >> ~/.ssh/authorized_keys", ["T1098.004"]),
    ("nano ~/.ssh/authorized_keys", ["T1098.004"]),
    ("crontab -l", ["T1053.003"]), ("useradd fake", ["T1136.001"]),
    ("history -c", ["T1070.003"]), ("rm ~/.bash_history", ["T1070.003"]),
    ("> ~/.zsh_history", ["T1070.003"]),
    ("sudo id", ["T1033", "T1548.003"]), ("sudo -n whoami", ["T1033", "T1548.003"]),
    ("./xmrig --help", ["T1496.001"]),
    ("wget http://127.0.0.1:11434/xmrig.tar.gz", ["T1105", "T1496.001"]),
    ("bash", ["T1059.004"]), ("/bin/sh -c 'uname'", ["T1059.004"]),
    ("whoami && uname -a; ls", ["T1033", "T1082", "T1083"]),
])
def test_positive_rules(line, expected):
    assert tag(line) == expected


@pytest.mark.parametrize("line", [
    "echo uname", "echo 'ls; whoami'", "echo /etc/passwd", "echo .env",
    "echo authorized_keys", 'echo ">" authorized_keys', "echo xmrig",
    "cat .env.example", "cat /etc/passwd.bak", "cat ~/.ssh/authorized_keys",
    "cat miner_notes.txt", "history", "ip route", "printf '%s' uname",
    "# uname", "", "   ", "cat 'unterminated", None,
    "web login probing", "login admin", "ssh admin@127.0.0.1",
])
def test_false_positives_and_malformed_input(line):
    assert tag(line) == []


def test_ids_are_unique_and_catalogue_is_pinned():
    assert tag("uname; hostname; uname") == ["T1082"]
    assert ATTACK_VERSION == "20.0"
    assert len(TECHNIQUES) == 16
    assert all("v20.0" in VERIFICATION[technique] for technique in TECHNIQUES)
