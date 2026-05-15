#!/usr/bin/env python
"""Start a game client."""
import argparse

import arcade

from app.scenes.lobby_scene import LobbyScene
from app.scenes.state_machine import SceneManager
from net.client import GameClient
from engine.config import DEFAULT_PORT
from engine.transport import make_client_transport
from engine.window import GameWindow


def main() -> None:
    parser = argparse.ArgumentParser(description="Explosion Boy client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--name", default="Player")
    parser.add_argument("--backend", default="tcp",
                        help="Transport backend (default: tcp)")
    args = parser.parse_args()

    transport = make_client_transport(
        args.backend, host=args.host, port=args.port
    )
    client = GameClient(transport)

    window = GameWindow()
    manager = SceneManager()
    manager.push(LobbyScene(client, args.name, manager))
    window.set_scene_manager(manager)

    arcade.run()

    client.stop()


if __name__ == "__main__":
    main()
