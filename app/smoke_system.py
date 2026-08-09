"""GLSL renderer for smoke-bomb clouds.

Purely a client-side effect: the server has no concept of per-player
visibility, so every client independently punches its own hole around
itself when drawing every cloud (including other players' smoke bombs).
Cloud lifetime is entirely server-driven via SmokeCloud.ticks_remaining/
ticks_total, so unlike the particle system there is no CPU simulation
here — only rendering. If the driver does not support GLSL 3.30
(OpenGL 3.3) the system disables itself silently so the rest of the
game is unaffected.
"""
from __future__ import annotations

import logging
from pathlib import Path

import arcade
from arcade.gl.geometry import quad_2d

from app.gfx_base import try_init_shader_effect
from core.state import GameState
from engine.config import TILE_SIZE

_log = logging.getLogger(__name__)

_SHADER_DIR = Path(__file__).parent.parent / 'resources' / 'shaders'

# Set to True by disable() before any GameView is created to skip all GL work.
_force_disabled: bool = False


def disable() -> None:
    """Permanently disable the smoke cloud effect (call before the first draw)."""
    global _force_disabled
    _force_disabled = True


_HOLE_RADIUS = TILE_SIZE       # 1 grid cell around the local player
_EDGE_SOFTNESS = 0.12          # fraction of the box half-extent softened at the boundary


class SmokeCloudSystem:
    """Renders every active SmokeCloud in GameState.smoke_clouds."""

    def __init__(self) -> None:
        self._program = None
        self._quad = None
        # None = not yet attempted; True = ready; False = permanently disabled
        self._enabled: bool | None = None

    def draw(self, state: GameState, player_x: float, player_y: float) -> None:
        """Draw every active smoke cloud, cutting a hole around (player_x, player_y)."""
        if not state.smoke_clouds:
            return
        if self._enabled is None:
            self._enabled = self._try_init()
        if not self._enabled:
            return

        ctx = arcade.get_window().ctx
        saved_blend = ctx.blend_func
        ctx.enable(ctx.BLEND)
        ctx.blend_func = ctx.BLEND_DEFAULT

        self._program['player_pos'] = (player_x, player_y)
        self._program['hole_radius'] = _HOLE_RADIUS
        self._program['edge_softness'] = _EDGE_SOFTNESS

        for cloud in state.smoke_clouds:
            cx = cloud.col * TILE_SIZE + TILE_SIZE / 2
            cy = cloud.row * TILE_SIZE + TILE_SIZE / 2
            side = (cloud.radius * 2 + 1) * TILE_SIZE
            life_ratio = 1.0 - (
                cloud.ticks_remaining / cloud.ticks_total if cloud.ticks_total else 0.0
            )

            self._program['center'] = (cx, cy)
            self._program['size'] = (side, side)
            self._program['life_ratio'] = life_ratio
            self._quad.render(self._program)

        ctx.blend_func = saved_blend

    def _try_init(self) -> bool:
        """Load the smoke shader and allocate GPU resources.

        Returns False on any failure so the effect degrades gracefully.
        """
        def build(ctx) -> None:
            vert_src = (_SHADER_DIR / 'smoke.vert').read_text()
            frag_src = (_SHADER_DIR / 'smoke.frag').read_text()
            self._program = ctx.program(vertex_shader=vert_src, fragment_shader=frag_src)
            self._quad = quad_2d(size=(1.0, 1.0))

        return try_init_shader_effect(_log, 'Smoke cloud effect', _force_disabled, build)
