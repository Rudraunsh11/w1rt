"""CanaryNet SSH Front Honeypot Server.

Listens strictly on 127.0.0.1:2222.
Provides authentic Ubuntu banner, interactive shell with session tracking,
runtime-generated host keys, and safe router execution.
"""

import asyncio
import os
import uuid
from typing import Dict, Optional, Tuple
import asyncssh
from canarynet.router import router
from canarynet.state.session import Session

DEFAULT_LOGINS = {
    "admin": "admin",
    "root": "root",
    "user": "password",
    "visitor": "canary",
    "guest": "guest",
}

DEFAULT_BANNER = (
    "Welcome to Ubuntu 22.04.1 LTS (GNU/Linux 5.15.0-58-generic x86_64)\r\n\r\n"
    " * Documentation:  https://help.ubuntu.com\r\n"
    " * Management:     https://landscape.canonical.com\r\n"
    " * Support:        https://ubuntu.com/advantage\r\n\r\n"
    "Last login: Fri Oct 16 10:14:02 2026 from 127.0.0.1\r\n"
)


class CanarySSHServer(asyncssh.SSHServer):
    """SSH server implementing fake logins and connection isolation."""

    def __init__(self, logins: Dict[str, str]):
        self.logins = logins
        self.authenticated_user = "admin"

    def password_auth_supported(self) -> bool:
        return True

    def validate_password(self, username: str, password: str) -> bool:
        # Accept credentials in the configured fake logins map
        # If password in logins matches, or user exists with non-empty password
        if username in self.logins:
            expected = self.logins[username]
            if not expected or expected == password:
                self.authenticated_user = username
                return True
        return False


def get_or_generate_host_key(key_path: str = "host_key.key") -> asyncssh.SSHKey:
    """Generates an in-memory or file-backed host key at runtime."""
    if os.path.exists(key_path):
        try:
            return asyncssh.read_private_key(key_path)
        except Exception:
            pass

    key = asyncssh.generate_private_key("ssh-rsa")
    try:
        key.write_private_key(key_path)
    except Exception:
        pass
    return key


def make_process_factory(logins: Dict[str, str], banner: str = DEFAULT_BANNER):
    """Creates an asyncssh process factory bound to session state."""

    async def process_factory(process: asyncssh.SSHServerProcess) -> None:
        peer = process.get_extra_info("peername")
        src_ip = peer[0] if peer and isinstance(peer, (tuple, list)) else "127.0.0.1"

        username = process.get_extra_info("username") or "admin"
        session_id = f"ssh-{uuid.uuid4().hex[:8]}"
        session = Session(session_id=session_id, user=username, src=src_ip)

        command = process.command
        if command:
            # Non-interactive command execution (e.g., ssh user@host "whoami")
            out = router.run(session, command)
            process.stdout.write(out)
            process.exit(0)
            return

        # Interactive terminal session
        process.stdout.write(banner)
        prompt = f"{session.user}@web-prod-01:{session.cwd}$ "
        process.stdout.write(prompt)

        while not process.stdin.at_eof():
            try:
                line = await process.stdin.readline()
            except Exception:
                break

            if not line:
                # EOF / Ctrl-D
                break

            clean_line = line.strip()
            if clean_line == "exit" or clean_line == "logout":
                process.stdout.write("logout\r\n")
                break

            if clean_line:
                output = router.run(session, clean_line)
                # Ensure CRLF line endings for raw SSH terminal
                crlf_output = output.replace("\r\n", "\n").replace("\n", "\r\n")
                process.stdout.write(crlf_output)

            prompt = f"{session.user}@web-prod-01:{session.cwd}$ "
            process.stdout.write(prompt)

        process.exit(0)

    return process_factory


async def create_ssh_server(
    host: str = "127.0.0.1",
    port: int = 2222,
    logins: Optional[Dict[str, str]] = None,
    banner: str = DEFAULT_BANNER,
    host_key: Optional[asyncssh.SSHKey] = None,
) -> asyncssh.SSHListener:
    """Creates and starts the CanaryNet SSH listener."""
    # STRICT SAFETY: Refuse any host except 127.0.0.1
    if host != "127.0.0.1":
        raise ValueError(
            f"Safety violation: CanaryNet SSH server must bind only to 127.0.0.1. Refused: {host}"
        )

    if logins is None:
        logins = DEFAULT_LOGINS

    if host_key is None:
        host_key = get_or_generate_host_key()

    server_factory = lambda: CanarySSHServer(logins)
    proc_factory = make_process_factory(logins, banner)

    listener = await asyncssh.create_server(
        server_factory=server_factory,
        host=host,
        port=port,
        server_host_keys=[host_key],
        process_factory=proc_factory,
        reuse_port=False,
    )
    return listener


def serve(host: str = "127.0.0.1", port: int = 2222) -> None:
    """Contract entrypoint: Starts the CanaryNet SSH honeypot."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        listener = loop.run_until_complete(create_ssh_server(host=host, port=port))
        print(f"CanaryNet SSH honeypot listening on {host}:{port}")
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        loop.close()
