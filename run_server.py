#!/usr/bin/env python
"""Start the authoritative game server."""
import argparse
import os

from net.server import GameServer
from engine.config import DEFAULT_PORT, MAX_PLAYERS
from engine.transport import make_server_transport


def main() -> None:
    parser = argparse.ArgumentParser(description="Explosion Boy server")
    parser.add_argument("--host", default=os.environ.get("SERVER_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SERVER_PORT", DEFAULT_PORT)))
    parser.add_argument("--backend", default=os.environ.get("SERVER_BACKEND", "tcp"),
                        help="Transport backend (default: tcp)")
    parser.add_argument("--debug", action="store_true",
                        help="Print input-buffer diagnostics each second")
    args = parser.parse_args()

    transport = make_server_transport(
        args.backend, host=args.host, port=args.port, max_clients=MAX_PLAYERS
    )
    print(f"Listening on {args.host}:{args.port} [{args.backend}]")
    GameServer(transport, debug=args.debug).run()


if __name__ == "__main__":
    main()
