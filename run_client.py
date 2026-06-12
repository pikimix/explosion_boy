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
from engine import user_prefs


def main() -> None:
    prefs = user_prefs.load()

    parser = argparse.ArgumentParser(description="Explosion Boy client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--name", default=prefs['name'])
    parser.add_argument("--backend", default="dual",
                        help="Transport backend (default: dual)")
    parser.add_argument("--no-shader", action="store_true",
                        help="Disable GLSL particle effects")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug overlays and controls")
    args = parser.parse_args()

    if args.no_shader:
        from app.particle_system import disable as _disable_particles
        _disable_particles()

    transport = make_client_transport(
        args.backend, host=args.host, port=args.port
    )
    client = GameClient(transport)

    colour_rgb = prefs['colour_rgb']
    colour_tuple = tuple(colour_rgb) if colour_rgb is not None else None

    window = GameWindow()
    manager = SceneManager()
    manager.push(LobbyScene(
        client, args.name, manager,
        volume=prefs['volume'],
        colour_rgb=colour_tuple,
        debug=args.debug,
    ))
    window.set_scene_manager(manager)

    arcade.run()

    user_prefs.save()
    client.stop()


if __name__ == "__main__":
    main()
