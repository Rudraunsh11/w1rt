import http.client
import json
import re
import threading
from urllib.parse import urlencode

import pytest

from canarynet.canary import registry
from canarynet.fronts import web


class Browser:
    def __init__(self, port):
        self.port = port
        self.cookie = ""

    def request(self, method="GET", path="/login", body=None, headers=None):
        supplied = {"Cookie": self.cookie}
        if body is not None:
            supplied["Content-Type"] = "application/x-www-form-urlencoded"
        supplied.update(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=supplied)
            response = conn.getresponse()
            text = response.read().decode()
            fields = dict(response.getheaders())
            if "Set-Cookie" in fields:
                self.cookie = fields["Set-Cookie"].split(";", 1)[0]
            return response.status, fields, text
        finally:
            conn.close()

    def csrf(self):
        status, _, page = self.request()
        assert status == 200
        return re.search(r'name="csrf" value="([^"]+)"', page).group(1)

    def login(self, username="admin", password="admin", csrf=None):
        return self.request("POST", "/login", urlencode({"csrf": csrf or self.csrf(), "username": username, "password": password}))


@pytest.fixture
def lab(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    registry._reset()
    events = []
    def capture(session_id, src, input, output, answered_by, latency_ms, tags):
        events.append(dict(session_id=session_id, src=src, input=input, output=output,
                           answered_by=answered_by, latency_ms=latency_ms, tags=tags))
    monkeypatch.setattr(web, "log_event", capture)
    server = web.create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, events, Browser(server.server_port)
    finally:
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
        registry._reset()


def test_login_dashboard_logout_and_cookie_rotation(lab):
    server, events, client = lab
    token = client.csrf()
    previous_cookie = client.cookie
    status, headers, _ = client.login(csrf=token)
    assert status == 303 and headers["Location"] == "/dashboard"
    assert client.cookie != previous_cookie
    status, _, page = client.request(path="/dashboard")
    assert status == 200 and "web-prod-01" in page
    assert "Application configuration" in page
    csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
    status, headers, _ = client.request("POST", "/logout", urlencode({"csrf": csrf}))
    assert status == 303 and headers["Location"] == "/login"
    assert client.request(path="/dashboard")[0] == 303
    assert [json.loads(e["output"])["event"] for e in events].count("login_success") == 1


def test_canary_reuse_is_linked_across_two_browsers_and_redacted(lab):
    server, events, original = lab
    assert original.request(path="/robots.txt")[0] == 200
    status, _, config = original.request(path="/backups/app.env")
    assert status == 200
    password = re.search(r"^DB_PASSWORD=(.+)$", config, re.M).group(1)
    planted_session = events[-1]["session_id"]
    reuse = Browser(server.server_port)
    assert reuse.login("webapp", password)[0] == 200
    alert_event = events[-1]
    alert = json.loads(alert_event["output"])
    assert alert["event"] == "canary_reuse" and alert["login_result"] == "denied"
    assert alert["planted_session"] == planted_session
    assert alert["canary_id"].startswith("cn-")
    assert alert_event["session_id"] != planted_session
    assert set(alert_event["tags"]) == {"T1552.001", "T1078"}
    assert password not in json.dumps(events)
    assert "webapp" not in alert_event["output"]
    assert reuse.request(path="/dashboard")[0] == 303


def test_each_browser_keeps_its_own_stable_fake_file(lab):
    server, _, a = lab
    first = a.request(path="/backups/app.env")[2]
    assert a.request(path="/backups/app.env")[2] == first
    b = Browser(server.server_port)
    assert b.request(path="/backups/app.env")[2] != first
    assert b.request(path="/dashboard")[0] == 303


def test_wrong_credentials_are_not_retained_or_reflected(lab):
    server, events, client = lab
    user = '<script>alert("visitor")</script>'
    password = "not-a-real-password-for-testing"
    _, _, page = client.login(user, password)
    assert "We could not sign you in" in page
    assert user not in page and password not in page
    assert user not in json.dumps(events) and password not in json.dumps(events)
    assert json.loads(events[-1]["output"])["event"] == "login_failed"
    assert not events[-1]["tags"]


@pytest.mark.parametrize("csrf", ["invalid", "\u2603"])
def test_invalid_csrf_never_logs_form_data(lab, csrf):
    _, events, client = lab
    assert client.login("private-name", "private-value", csrf=csrf)[0] == 403
    assert "private-" not in json.dumps(events)


def test_external_origin_host_and_oversized_body_are_rejected(lab):
    _, events, client = lab
    token = client.csrf()
    form = urlencode({"csrf": token, "username": "admin", "password": "admin"})
    assert client.request("POST", "/login", form, {"Origin": "null"})[0] == 403
    assert client.request(headers={"Host": "untrusted.invalid"})[0] == 421
    assert client.request("POST", "/login", "x" * (web.MAX_BODY + 1))[0] == 400
    assert client.request("POST", "/login", form, {"Content-Type": "application/json"})[0] == 400
    assert "private-" not in json.dumps(events)


def test_valid_same_origin_and_unicode_credentials(lab):
    server, events, client = lab
    token = client.csrf()
    form = urlencode({"csrf": token, "username": "admin", "password": "admin"})
    origin = f"http://127.0.0.1:{server.server_port}"
    assert client.request("POST", "/login", form, {"Origin": origin})[0] == 303
    other = Browser(server.server_port)
    assert other.login("\u2603", "\u2603")[0] == 200
    assert "\\u2603" not in json.dumps(events)


def test_cookie_security_and_no_external_assets(lab):
    _, _, client = lab
    _, headers, page = client.request()
    assert "HttpOnly" in headers["Set-Cookie"] and "SameSite=Strict" in headers["Set-Cookie"]
    assert headers["Cache-Control"] == "no-store"
    # Ordinary browser form posts must retain their Origin for the origin check.
    assert headers["Referrer-Policy"] == "same-origin"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert '<script' not in page and 'src="http' not in page
    assert "DB_PASSWORD" not in page
    client.cookie = "ops_visit=chosen-by-visitor"
    assert client.request()[0] == 200
    assert client.cookie != "ops_visit=chosen-by-visitor"


def test_expired_sessions_and_capacity(lab, monkeypatch):
    server, _, client = lab
    client.csrf()
    old_cookie = client.cookie
    monkeypatch.setattr(web, "MAX_VISITS", 1)
    assert Browser(server.server_port).request()[0] == 503
    with server.visit_lock:
        for visit in server.visits.values():
            visit.touched -= web.SESSION_TTL + 1
    assert client.request()[0] == 200
    assert client.cookie != old_cookie


def test_loopback_only_and_fixed_fake_paths():
    with pytest.raises(ValueError, match="127.0.0.1"):
        web.create_server(host="10.0.0.1", port=0)


def test_web_events_generate_existing_html_report(lab, monkeypatch, tmp_path):
    from canarynet.logger import log_event
    from canarynet.report import generate_report
    _, _, client = lab
    monkeypatch.setattr(web, "log_event", log_event)
    _, _, config = client.request(path="/backups/app.env")
    password = re.search(r"^DB_PASSWORD=(.+)$", config, re.M).group(1)
    client.login("webapp", password)
    report = tmp_path / "report.html"
    generate_report(output_path=report)
    contents = report.read_text()
    logs = (tmp_path / "logs/events.jsonl").read_text()
    assert "canary_reuse" in contents and "planted_session" in contents
    assert "T1078" in contents
    assert password not in logs and password not in contents
    assert all(e["answered_by"] == "code" for e in map(json.loads, logs.splitlines()))


def test_query_strings_and_unknown_paths_do_not_leak_into_logs(lab):
    _, events, client = lab
    client.request(path="/login?password=private-query")
    assert client.request(path="/missing/private-path")[0] == 404
    assert client.request(path="/backups/../../etc/passwd")[0] == 404
    assert "private-query" not in json.dumps(events)
    assert "private-path" not in json.dumps(events)
