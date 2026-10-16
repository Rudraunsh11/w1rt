import pytest

from canarynet.canary import registry
from canarynet.state.session import Session


@pytest.fixture(autouse=True)
def clean():
    registry._reset()
    yield
    registry._reset()


def _by_kind(records):
    return {r["kind"]: r for r in records}


def test_plant_writes_both_files_with_tokens():
    s = Session("s1", src="127.0.0.1")
    recs = _by_kind(registry.plant(s))
    assert set(recs) == {"env_db", "aws"}
    env = s.read_file("/var/www/html/.env")
    assert f"DB_PASSWORD={recs['env_db']['secret']}" in env
    aws = s.read_file("~/.aws/credentials")
    assert recs["aws"]["username"] in aws and recs["aws"]["secret"] in aws
    assert recs["aws"]["path"] == "/home/admin/.aws/credentials"
    assert ".aws" in s.listdir("~")


def test_token_formats():
    recs = _by_kind(registry.plant(Session("s1")))
    key_id, secret = recs["aws"]["username"], recs["aws"]["secret"]
    assert key_id.startswith("AKIA") and len(key_id) == 20 and key_id.isalnum()
    assert len(secret) == 40
    assert len(recs["env_db"]["secret"]) == 20


def test_unique_per_session_and_idempotent():
    a, b = Session("a"), Session("b")
    ra, rb = _by_kind(registry.plant(a)), _by_kind(registry.plant(b))
    assert ra["env_db"]["secret"] != rb["env_db"]["secret"]
    assert ra["aws"]["secret"] != rb["aws"]["secret"]
    assert _by_kind(registry.plant(a))["aws"]["secret"] == ra["aws"]["secret"]  # same again


def test_check_db_password_reuse_any_username():
    s = Session("s1", src="10.0.0.5")
    db = _by_kind(registry.plant(s))["env_db"]
    hit = registry.check("root", db["secret"], "10.0.0.9")
    assert hit["kind"] == "env_db" and hit["matched"] == "password"
    assert hit["planted_session"] == "s1" and hit["planted_src"] == "10.0.0.5"
    assert hit["reused_src"] == "10.0.0.9" and hit["reused_username"] == "root"
    assert hit["tags"] == ["T1552.001", "T1078"]
    assert "secret" not in hit  # alert does not echo the secret


def test_check_aws_key_pair_and_key_id_alone():
    aws = _by_kind(registry.plant(Session("s1")))["aws"]
    assert registry.check(aws["username"], aws["secret"], "x")["matched"] == "password"
    assert registry.check(aws["username"], "wrong", "x")["matched"] == "username"


def test_check_misses():
    registry.plant(Session("s1"))
    assert registry.check("admin", "admin", "x") is None
    assert registry.check("admin", "", "x") is None
    assert registry.check(None, None, "x") is None


def test_check_result_is_a_copy():
    db = _by_kind(registry.plant(Session("s1")))["env_db"]
    hit = registry.check("u", db["secret"], "x")
    hit["tags"].append("tampered")
    assert registry.check("u", db["secret"], "x")["tags"] == ["T1552.001", "T1078"]


def test_missing_web_root_plants_only_aws():
    s = Session("s1", fs={"/": {"type": "dir", "content": ""},
                          "/home": {"type": "dir", "content": ""},
                          "/home/admin": {"type": "dir", "content": ""}})
    assert set(_by_kind(registry.plant(s))) == {"aws"}
