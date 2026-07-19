#!/usr/bin/env python
"""Start the authoritative game server."""
import argparse
import os

from net.server import GameServer
from engine.config import DEFAULT_PORT, MAX_PLAYERS, TICK_RATE, ROLLBACK_BUFFER_SIZE
from engine.transport import make_server_transport


def main() -> None:
    """Parse CLI arguments, build the transport, and run the game server."""
    parser = argparse.ArgumentParser(description="Explosion Boy server")
    parser.add_argument("--host", default=os.environ.get("SERVER_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("SERVER_PORT", DEFAULT_PORT)))
    parser.add_argument("--backend", default=os.environ.get("SERVER_BACKEND", "dual"),
                        help="Transport backend (default: dual)")
    parser.add_argument("--tick-rate", type=int, default=TICK_RATE,
                        help=f"Server tick rate in tps (default: {TICK_RATE})")
    parser.add_argument("--rollback-buffer", type=int, default=ROLLBACK_BUFFER_SIZE,
                        help=f"Number of ticks to keep for rollback (default: {ROLLBACK_BUFFER_SIZE})")
    parser.add_argument("--debug", action="store_true",
                        help="Print input-buffer diagnostics each second")
    args = parser.parse_args()

    transport = make_server_transport(
        args.backend, host=args.host, port=args.port, max_clients=MAX_PLAYERS
    )
    print(f"Listening on {args.host}:{args.port} [{args.backend}]")
    GameServer(
        transport,
        tick_rate=args.tick_rate,
        rollback_buffer_size=args.rollback_buffer,
        debug=args.debug,
    ).run()


if __name__ == "__main__":
    main()
