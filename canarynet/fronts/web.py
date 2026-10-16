"""Local web decoy. Fake accounts/files only; no model or outbound requests.

The standard-library HTTP server is for this controlled loopback demo only.
Canary records are shared with other fronts only in the same Python process.
"""
from __future__ import annotations

import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from html import escape
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from canarynet.canary import registry
from canarynet.logger import log_event
from canarynet.state.session import Session

MAX_BODY = 4096
MAX_VISITS = 128
SESSION_TTL = 1800
COOKIE_NAME = "ops_visit"

_STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f3f5f8;color:#15233b;font:15px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
a{color:#176b70;text-decoration:none}a:hover{text-decoration:underline}button,input{font:inherit}
.bar{height:76px;border-bottom:1px solid #dde3eb;background:white;display:flex;align-items:center;justify-content:space-between;padding:0 7%}
.brand{font-size:20px;font-weight:750;letter-spacing:-.7px}.brand span{color:#23878b}.service{font-size:12px;color:#637189}.service b{color:#16846d}
.layout{max-width:1160px;margin:65px auto;display:grid;grid-template-columns:1.05fr 1fr;gap:70px;padding:0 32px;align-items:center}
.eyebrow{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#23878b;font-weight:750}h1{font-size:48px;line-height:1.1;letter-spacing:-2px;margin:20px 0}h2{font-size:25px;margin:0 0 12px;letter-spacing:-.7px}
.lede{color:#68768c;line-height:1.8;max-width:400px;font-size:16px}.features{margin-top:36px;border-top:1px solid #dce3ed;padding-top:22px;display:flex;gap:34px}.features strong{display:block;font-size:13px}.features span{display:block;margin-top:8px;color:#748095;font-size:12px}
.card{background:white;border:1px solid #dfe5ed;border-radius:18px;padding:36px;box-shadow:0 20px 60px #132b4d0a}.muted{color:#758198;font-size:13px;line-height:1.7}
label{display:block;font-size:12px;font-weight:700;margin:22px 0 9px}input{width:100%;padding:13px 14px;border:1px solid #cfd8e4;border-radius:8px;background:#fbfcfe;color:#15233b}input:focus{outline:2px solid #80c8c4;outline-offset:2px}
.primary{width:100%;border:0;background:#176b70;color:white;border-radius:8px;padding:14px;margin-top:25px;font-weight:700;cursor:pointer}.primary:hover{background:#10555a}.footnote{font-size:11px;line-height:1.7;color:#8a94a4;margin-top:22px;text-align:center}
.error{background:#fff3ee;border:1px solid #f4d0bd;color:#9b3b1c;border-radius:8px;padding:12px;margin-top:20px;font-size:13px}
.footer{max-width:1096px;padding:24px 0;margin:0 auto;border-top:1px solid #dce3ed;display:flex;justify-content:space-between;color:#8994a4;font-size:11px}
.dashboard{max-width:1100px;padding:0 28px;margin:48px auto}.dashboard h1{font-size:36px}.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin:28px 0}.tile{padding:25px;background:white;border:1px solid #dfe5ed;border-radius:12px}.tile strong{display:block;font-size:25px;margin-top:14px}.tile small{color:#748095}
.resource{padding:25px;background:white;border:1px solid #dfe5ed;border-radius:12px;margin-top:20px;display:flex;align-items:center;justify-content:space-between}.resource p{color:#748095;font-size:13px}.quiet{background:white;border:1px solid #ccd7e5;padding:9px 16px;border-radius:7px;color:#516078;cursor:pointer}
@media(max-width:760px){.layout{grid-template-columns:1fr;gap:28px;margin:30px auto}.layout h1{font-size:36px}.features{display:none}.footer{margin:0 32px}.tiles{grid-template-columns:1fr}.service{display:none}.card{padding:27px}.resource{display:block}.bar{padding:0 28px}}
"""


def _page(content, *, signed_in=False, csrf=""):
    right = '<span class="service"><b>Operational</b> &nbsp; Identity gateway</span>'
    if signed_in:
        right = (f'<form method="post" action="/logout"><input type="hidden" name="csrf" value="{escape(csrf)}">'
                 '<button class="quiet" type="submit">Sign out</button></form>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Operations | Workspace access</title>'
            f'<style>{_STYLE}</style></head><body><header class="bar">'
            f'<div class="brand">ops<span>/</span>workspace</div>{right}</header>{content}'
            '<footer class="footer"><span>Operations platform · Internal services</span>'
            '<span>Workspace gateway / v2.4</span></footer></body></html>')


def _login_page(csrf, error=False):
    message = '<div class="error" role="alert">We could not sign you in. Check your details and try again.</div>' if error else ''
    return _page('<main class="layout"><section><div class="eyebrow">Workspace administration</div>'
                 '<h1>Your operations.<br>One workspace.</h1>'
                 '<p class="lede">Access infrastructure settings, application resources and environment configuration from your operations workspace.</p>'
                 '<div class="features"><div><strong>Centralised access</strong><span>One place for your services</span></div>'
                 '<div><strong>Environment controls</strong><span>Configuration and resources</span></div></div></section>'
                 '<section class="card"><h2>Welcome back</h2><div class="muted">Sign in to your workspace to continue.</div>'
                 f'{message}<form method="post" action="/login" autocomplete="off">'
                 f'<input type="hidden" name="csrf" value="{escape(csrf)}">'
                 '<label for="username">Workspace username</label><input id="username" name="username" required maxlength="80" autocomplete="off" placeholder="Enter your username">'
                 '<label for="password">Password</label><input id="password" name="password" type="password" required maxlength="256" autocomplete="off" placeholder="Enter your password">'
                 '<button class="primary" type="submit">Sign in to workspace</button></form>'
                 '<div class="footnote">Authorised personnel only. Access activity may be recorded.</div></section></main>')


def _dashboard(visit):
    host = escape(visit.session.env.get("HOSTNAME", "web-prod-01"))
    return _page('<main class="dashboard"><div class="eyebrow">Infrastructure overview</div>'
                 '<h1>Welcome to your workspace.</h1><p class="muted">Review the application environment and workspace resources.</p>'
                 '<div class="tiles"><section class="tile"><small>APPLICATION HOST</small>'
                 f'<strong>{host}</strong></section><section class="tile"><small>ENVIRONMENT</small><strong>Production</strong></section>'
                 '<section class="tile"><small>WORKSPACE USER</small><strong>admin</strong></section></div>'
                 '<section class="resource"><div><h2>Application configuration</h2><p>Environment snapshot for the current application workspace.</p></div>'
                 '<a href="/backups/app.env">View configuration backup</a></section>'
                 '<section class="resource"><div><h2>Workspace activity</h2><p>Configuration views and access requests are recorded by the gateway.</p></div>'
                 '<span class="muted">Audit collection enabled</span></section></main>', signed_in=True, csrf=visit.csrf)


@dataclass
class _Visit:
    session: Session
    csrf: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    authenticated: bool = False
    touched: float = field(default_factory=time.monotonic)
    lock: object = field(default_factory=threading.Lock)


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        self.visits = {}
        self.visit_lock = threading.Lock()
        super().__init__(address, _Handler)

    def visit(self, cookie, src):
        token = None
        try:
            parsed = SimpleCookie()
            if len(cookie) <= MAX_BODY:
                parsed.load(cookie)
                if COOKIE_NAME in parsed:
                    token = parsed[COOKIE_NAME].value
        except CookieError:
            pass
        now = time.monotonic()
        with self.visit_lock:
            for stale in [k for k, v in self.visits.items() if now - v.touched > SESSION_TTL]:
                del self.visits[stale]
            if token in self.visits:
                visit = self.visits[token]
                visit.touched = now
                return token, visit
            if len(self.visits) >= MAX_VISITS:
                return None, None
            token = secrets.token_urlsafe(32)
            session = Session("web-" + secrets.token_hex(8), user="admin", src=src)
            registry.plant(session)
            visit = _Visit(session)
            self.visits[token] = visit
            return token, visit

    def rotate(self, token, visit):
        with self.visit_lock:
            self.visits.pop(token, None)
            token = secrets.token_urlsafe(32)
            visit.csrf = secrets.token_urlsafe(24)
            self.visits[token] = visit
            return token


class _Handler(BaseHTTPRequestHandler):
    server_version = "WorkspaceGateway"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        # Central logging below deliberately excludes query strings and form data.
        pass

    def _response(self, status, body="", *, kind="text/html; charset=utf-8", location=None):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Connection", "close")
        if getattr(self, "token", None):
            self.send_header("Set-Cookie", f"{COOKIE_NAME}={self.token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL}")
        if location:
            self.send_header("Location", location)
        self.end_headers()
        self.wfile.write(data)
        self.close_connection = True

    def _start(self):
        self.started = time.perf_counter()
        port = self.server.server_port
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            allowed.update({"127.0.0.1", "localhost"})
        if self.headers.get("Host", "") not in allowed:
            self._response(421, "Invalid host", kind="text/plain; charset=utf-8")
            return False
        self.token, self.visitor = self.server.visit(self.headers.get("Cookie", ""), self.client_address[0])
        if self.visitor is None:
            self._response(503, "Workspace busy. Try again later.", kind="text/plain; charset=utf-8")
            return False
        return True

    def _event(self, route, event, tags=None, **details):
        output = json.dumps({"event": event, **details}, ensure_ascii=False)
        log_event(self.visitor.session.session_id, self.client_address[0], route,
                  output, "code", round((time.perf_counter() - self.started) * 1000, 2), tags or [])

    def do_GET(self):
        if not self._start():
            return
        path = self.path.partition("?")[0]
        with self.visitor.lock:
            if path in {"/", "/login"}:
                self._event("GET /login", "page_view")
                if self.visitor.authenticated:
                    self._response(303, location="/dashboard")
                else:
                    self._response(200, _login_page(self.visitor.csrf))
            elif path == "/dashboard":
                self._event("GET /dashboard", "dashboard_view" if self.visitor.authenticated else "access_denied")
                if self.visitor.authenticated:
                    self._response(200, _dashboard(self.visitor))
                else:
                    self._response(303, location="/login")
            elif path == "/robots.txt":
                self._event("GET /robots.txt", "discovery")
                self._response(200, "User-agent: *\nDisallow: /backups/\n", kind="text/plain; charset=utf-8")
            elif path == "/backups/":
                self._event("GET /backups/", "backup_index_view")
                self._response(200, _page('<main class="dashboard"><h1>Environment snapshots</h1><section class="card"><a href="/backups/app.env">app.env</a></section></main>'))
            elif path == "/backups/app.env":
                self._event("GET /backups/app.env", "canary_file_view", ["T1552.001"])
                self._response(200, self.visitor.session.read_file("/var/www/html/.env") or "", kind="text/plain; charset=utf-8")
            else:
                self._event("GET unknown route", "not_found")
                self._response(404, _page('<main class="dashboard"><h1>Page not found</h1><a href="/login">Return to workspace access</a></main>'))

    def do_POST(self):
        if not self._start():
            return
        path = self.path.partition("?")[0]
        with self.visitor.lock:
            if path not in {"/login", "/logout"}:
                self._event("POST unknown route", "not_found")
                self._response(404, "Not found", kind="text/plain; charset=utf-8")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise ValueError
                if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
                    raise ValueError
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError
                values = parse_qs(raw.decode("utf-8"), keep_blank_values=True, strict_parsing=True, max_num_fields=8)
                required = {"csrf", "username", "password"} if path == "/login" else {"csrf"}
                if set(values) != required or any(len(v) != 1 for v in values.values()):
                    raise ValueError
                form = {k: v[0] for k, v in values.items()}
                if len(form["csrf"]) > 128 or len(form.get("username", "")) > 80 or len(form.get("password", "")) > 256:
                    raise ValueError
            except (ValueError, UnicodeError):
                self._event(f"POST {path}", "invalid_request")
                self._response(400, "Invalid request", kind="text/plain; charset=utf-8")
                return
            origin = self.headers.get("Origin")
            try:
                source = urlsplit(origin) if origin else None
                bad_origin = source is not None and (source.scheme != "http"
                    or source.netloc != self.headers["Host"]
                    or bool(source.path or source.query or source.fragment))
            except ValueError:
                bad_origin = True
            valid_csrf = not bad_origin and hmac.compare_digest(form["csrf"].encode(), self.visitor.csrf.encode())
            if not valid_csrf:
                self._event(f"POST {path}", "request_rejected")
                self._response(403, "Request rejected", kind="text/plain; charset=utf-8")
                return
            if path == "/logout":
                self._event("POST /logout", "logout")
                self.visitor.authenticated = False
                self.token = self.server.rotate(self.token, self.visitor)
                self._response(303, location="/login")
                return
            # Submitted passwords are checked in memory, never retained in visits or logs.
            hit = registry.check(form["username"], form["password"], self.client_address[0])
            allowed = (hmac.compare_digest(form["username"].encode(), b"admin")
                       and hmac.compare_digest(form["password"].encode(), b"admin"))
            if hit:
                self._event("POST /login", "canary_reuse", hit["tags"], canary_id=hit["canary_id"],
                            planted_session=hit["planted_session"], planted_src=hit["planted_src"],
                            matched=hit["matched"], login_result="denied")
                allowed = False
            else:
                self._event("POST /login", "login_success" if allowed else "login_failed")
            if allowed:
                self.visitor.authenticated = True
                self.token = self.server.rotate(self.token, self.visitor)
                self._response(303, location="/dashboard")
            else:
                self._response(200, _login_page(self.visitor.csrf, error=True))


def create_server(host="127.0.0.1", port=8080):
    """Create the lab listener; port=0 supports isolated loopback tests."""
    if host != "127.0.0.1":
        raise ValueError("The web decoy must bind only to 127.0.0.1")
    return _Server((host, port))


def serve(host="127.0.0.1", port=8080):
    """CONTRACT entrypoint. This serves the web front only, not the SSH front."""
    server = create_server(host, port)
    try:
        print(f"Web decoy: http://127.0.0.1:{server.server_port} (fake admin/admin)", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
