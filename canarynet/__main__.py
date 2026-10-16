"""Start CanaryNet Lite:  python -m canarynet [--port 2222]

Always binds 127.0.0.1 (there is deliberately no --host option).
"""
from __future__ import annotations

import argparse
import sys

from canarynet.router import router


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="canarynet", description="CanaryNet Lite SSH decoy (loopback only)")
    parser.add_argument("--port", type=int, default=2222)
    args = parser.parse_args(argv)

    if router.STANDINS:
        print("WARNING: running with stand-ins (not merged yet): " + ", ".join(router.STANDINS),
              file=sys.stderr)

    from canarynet.fronts.ssh import serve  # imported here so the rest works without asyncssh

    serve(host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
