#!/usr/bin/env python
"""Start the authoritative game server."""
import argparse

from net.server import GameServer
from engine.config import DEFAULT_PORT, MAX_PLAYERS
from engine.transport import make_server_transport


def main() -> None:
    parser = argparse.ArgumentParser(description="Explosion Boy server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--backend", default="tcp",
                        help="Transport backend (default: tcp)")
    args = parser.parse_args()

    transport = make_server_transport(
        args.backend, host=args.host, port=args.port, max_clients=MAX_PLAYERS
    )
    print(f"Listening on {args.host}:{args.port} [{args.backend}]")
    GameServer(transport).run()


if __name__ == "__main__":
    main()
