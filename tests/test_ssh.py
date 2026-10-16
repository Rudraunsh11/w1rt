"""Tests for CanaryNet SSH Front."""

import asyncio
import pytest
import asyncssh
from canarynet.fronts.ssh import create_ssh_server, DEFAULT_LOGINS


@pytest.mark.asyncio
async def test_ssh_safety_binding_refusal():
    """Verifies that binding to any host other than 127.0.0.1 is rejected immediately."""
    with pytest.raises(ValueError, match="Safety violation"):
        await create_ssh_server(host="0.0.0.0", port=2223)

    with pytest.raises(ValueError, match="Safety violation"):
        await create_ssh_server(host="192.168.1.10", port=2223)


@pytest.mark.asyncio
async def test_ssh_client_login_and_whoami():
    """An asyncssh client logs in to 127.0.0.1 on a test port, runs whoami, and gets an answer."""
    port = 22224  # Use distinct test port
    host_key = asyncssh.generate_private_key("ssh-rsa")

    server = await create_ssh_server(
        host="127.0.0.1",
        port=port,
        logins={"admin": "canarypass"},
        host_key=host_key,
    )

    try:
        # Connect via asyncssh client
        async with asyncssh.connect(
            host="127.0.0.1",
            port=port,
            username="admin",
            password="canarypass",
            known_hosts=None,
        ) as conn:
            # 1. Non-interactive command execution
            result = await conn.run("whoami", check=True)
            assert "admin" in result.stdout

            # 2. Interactive shell session
            async with conn.create_process() as proc:
                # Read banner & initial prompt
                initial_output = await proc.stdout.readuntil("$ ")
                assert "Ubuntu 22.04" in initial_output

                # Send command
                proc.stdin.write("id\n")
                id_output = await proc.stdout.readuntil("$ ")
                assert "uid=1000(admin)" in id_output

                # Send exit
                proc.stdin.write("exit\n")
                await proc.wait()
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_ssh_invalid_credentials_rejected():
    """Verifies that unapproved credentials fail authentication."""
    port = 22225
    host_key = asyncssh.generate_private_key("ssh-rsa")

    server = await create_ssh_server(
        host="127.0.0.1",
        port=port,
        logins={"admin": "correct_pass"},
        host_key=host_key,
    )

    try:
        with pytest.raises(asyncssh.PermissionDenied):
            await asyncssh.connect(
                host="127.0.0.1",
                port=port,
                username="admin",
                password="wrong_password",
                known_hosts=None,
            )
    finally:
        server.close()
        await server.wait_closed()
